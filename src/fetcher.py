import io
import os
import re
import json
import gzip
import math
import time
import zipfile
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Iterable, Tuple

from src.config import Config, ZoneConfig
from src.timeutil import format_relative_time, normalize_ts, paris_now

ODS_API_BASE = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
FIELDS_SELECT = "id,adresse,ville,cp,geom,prix,rupture,horaires"
# Flux XML d'origine du ministère (celui dont l'API Opendatasoft n'est qu'une copie) : seconde source de recoupement
OFFICIAL_FEED_URL = "https://donnees.roulez-eco.fr/opendata/instantane_ruptures"

PAGE_SIZE = 100
HTTP_ATTEMPTS = 3
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance géodésique rapide en km entre deux points GPS (modèle Gasoil Now)."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return round(R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)), 1)

def http_get(url: str, timeout: int = 15, attempts: int = HTTP_ATTEMPTS) -> bytes:
    """GET avec reprises (2s, 4s). Lève la dernière exception si toutes les tentatives échouent."""
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(2 * attempt)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SP-Bot/2.0", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as e:
            last_error = e
    raise last_error  # type: ignore[misc]

def _as_list(raw: Any) -> List[dict]:
    """Le flux sérialise un élément unique en objet et plusieurs en tableau : on normalise en liste."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]

def opening_label(automate: bool, hours: Dict[Any, List[List[str]]], now: Optional[datetime] = None) -> str:
    """Indique si l'on peut réellement se servir maintenant ('' si les horaires sont inconnus)."""
    hours = {int(k): v for k, v in (hours or {}).items()}  # les clés deviennent des chaînes après un passage en JSON
    if automate:
        return "Automate 24h/24"
    if not hours:
        return ""
    now = now or paris_now()
    hhmm = now.strftime("%H.%M")
    today = hours.get(now.isoweekday())
    if today is None:
        return ""
    for start, end in today:
        if start == end:
            return "Ouvert 24h/24"
        # Une plage dont la fermeture précède l'ouverture se termine après minuit
        if (start <= hhmm < end) or (end < start and hhmm >= start):
            return f"Ouvert jusqu'à {end.replace('.', 'h')}"
    for start, _ in today:
        if hhmm < start:
            return f"Fermé · ouvre à {start.replace('.', 'h')}"
    for offset in range(1, 8):
        day = now + timedelta(days=offset)
        slots = hours.get(day.isoweekday())
        if slots is None:
            return "Fermé actuellement"
        if slots:
            label = "demain" if offset == 1 else JOURS[day.isoweekday() - 1]
            return f"Fermé · ouvre {label} à {slots[0][0].replace('.', 'h')}"
    return "Fermé actuellement"

@dataclass
class Station:
    id: int
    brand: str
    address: str
    city: str
    postal_code: str
    latitude: float
    longitude: float
    distance_km: float
    zone_name: str
    status: str  # "DISPONIBLE", "RUPTURE_PARTIELLE", "RUPTURE_TOTALE"
    disponibles: List[str]
    rupture_temporaire: List[str]
    rupture_definitive: List[str]
    prices: Dict[str, Dict[str, Any]]
    google_maps_url: str
    waze_url: str
    ruptures_detail: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    automate_24_24: bool = False
    # Horaires par jour ISO (1 = lundi) : liste de plages ["07.00", "18.00"], [] si fermé. Jour absent = inconnu.
    hours: Dict[int, List[List[str]]] = field(default_factory=dict)

    def fuel_observation(self, fuel: str) -> Tuple[bool, str, Optional[float]]:
        """(disponible, horodatage de la déclaration, prix) pour un carburant.
        Disponible = prix valide publié ET aucune rupture en cours déclarée."""
        if fuel in self.disponibles:
            p = self.prices.get(fuel) or {}
            return True, normalize_ts(p.get("maj")), p.get("valeur")
        r = self.ruptures_detail.get(fuel) or {}
        return False, normalize_ts(r.get("debut")), None

    def opening_label(self, now: Optional[datetime] = None) -> str:
        return opening_label(self.automate_24_24, self.hours, now)

def build_station(sid: int, brand: str, address: str, city: str, postal_code: str,
                  lat: float, lon: float, distance_km: float, zone_name: str,
                  prix_items: Iterable[dict], rupture_items: Iterable[dict],
                  automate: bool = False, hours: Optional[Dict[int, List[List[str]]]] = None) -> Station:
    """Construit une station à partir des éléments bruts <prix>/<rupture> (clés nom, valeur, maj, debut, fin, type)."""
    ruptures: Dict[str, Dict[str, Any]] = {}
    for r in rupture_items:
        nom = r.get("nom")
        if nom and not r.get("fin"):  # une rupture avec date de fin est terminée
            ruptures[nom] = {"debut": normalize_ts(r.get("debut")), "type": r.get("type") or ""}

    prices: Dict[str, Dict[str, Any]] = {}
    for p in prix_items:
        nom, maj = p.get("nom"), normalize_ts(p.get("maj"))
        try:
            val = float(p.get("valeur"))
        except (TypeError, ValueError):
            continue
        if nom and val > 0 and maj:
            prices[nom] = {"valeur": val, "maj": maj, "relative_time": format_relative_time(maj)}

    # Un carburant n'est considéré en stock que s'il a un prix daté et aucune rupture en cours
    dispos = [f for f in prices if f not in ruptures]
    rupt_temp = [f for f, r in ruptures.items() if r["type"] != "definitive"]
    rupt_def = [f for f, r in ruptures.items() if r["type"] == "definitive"]
    status = "RUPTURE_TOTALE" if not dispos else ("RUPTURE_PARTIELLE" if rupt_temp else "DISPONIBLE")

    return Station(
        id=sid, brand=brand, address=address, city=city, postal_code=postal_code,
        latitude=lat, longitude=lon, distance_km=distance_km, zone_name=zone_name,
        status=status, disponibles=dispos, rupture_temporaire=rupt_temp, rupture_definitive=rupt_def,
        prices=prices,
        google_maps_url=f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
        waze_url=f"https://waze.com/ul?ll={lat},{lon}&navigate=yes",
        ruptures_detail=ruptures, automate_24_24=automate, hours=hours or {}
    )

def _strip_at(items: List[dict]) -> List[dict]:
    return [{k.lstrip("@"): v for k, v in item.items()} for item in items]

def _parse_hours(jours: List[dict]) -> Dict[int, List[List[str]]]:
    hours: Dict[int, List[List[str]]] = {}
    for j in jours:
        try:
            day = int(j.get("id"))
        except (TypeError, ValueError):
            continue
        slots = [[h.get("ouverture"), h.get("fermeture")] for h in j.get("horaire", [])
                 if h.get("ouverture") and h.get("fermeture")]
        if j.get("ferme"):
            hours[day] = []
        elif slots:
            hours[day] = sorted(slots)
    return hours

def _parse_ods_hours(raw: Any) -> Tuple[bool, Dict[int, List[List[str]]]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return False, {}
    if not isinstance(raw, dict):
        return False, {}
    jours = []
    for j in _strip_at(_as_list(raw.get("jour"))):
        j["horaire"] = _strip_at(_as_list(j.get("horaire")))
        jours.append(j)
    return bool(raw.get("@automate-24-24")), _parse_hours(jours)

@dataclass
class FetchResult:
    stations: List[Station] = field(default_factory=list)
    failed_zones: List[str] = field(default_factory=list)
    zones_total: int = 0

    @property
    def complete(self) -> bool:
        return not self.failed_zones

    @property
    def ok(self) -> bool:
        """Au moins une zone a répondu correctement."""
        return len(self.failed_zones) < self.zones_total

class FuelFetcher:
    """Récupérateur haute performance et multi-zones pour Vesoul, Belfort, Lure, Montbéliard."""
    def __init__(self, data_dir: str = "data"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, data_dir) if not os.path.isabs(data_dir) else data_dir
        self.stations_bundle = os.path.join(self.data_dir, "total_stations.json")
        self._brands_cache: Optional[Dict[int, str]] = None

    def get_brands_map(self) -> Dict[int, str]:
        """Charge le référentiel des 2327 stations Total en France (55 Ko)."""
        if self._brands_cache is not None:
            return self._brands_cache

        if os.path.exists(self.stations_bundle):
            try:
                with open(self.stations_bundle, "r", encoding="utf-8") as f:
                    self._brands_cache = {int(k): v for k, v in json.load(f).items()}
                    return self._brands_cache
            except Exception as e:
                print(f"[!] Erreur bundle total_stations: {e}")

        self._brands_cache = {}
        return self._brands_cache

    def _query_ods(self, where_clause: str) -> Optional[List[dict]]:
        """Retourne tous les enregistrements de la zone, ou None si l'API n'a pas répondu correctement.
        Une panne ne doit jamais être confondue avec « aucune station »."""
        records: List[dict] = []
        try:
            while True:
                params = urllib.parse.urlencode({
                    "where": where_clause,
                    "select": FIELDS_SELECT,
                    "order_by": "id",
                    "limit": PAGE_SIZE,
                    "offset": len(records)
                })
                data = json.loads(http_get(f"{ODS_API_BASE}?{params}").decode("utf-8"))
                page = data.get("results")
                if not isinstance(page, list) or not isinstance(data.get("total_count"), int):
                    raise ValueError("réponse inattendue (pas de champ results/total_count)")
                records.extend(page)
                if not page or len(records) >= data["total_count"]:
                    return records
        except Exception as e:
            print(f"[!] Erreur API ODS: {e}")
            return None

    def fetch(self, config: Config) -> FetchResult:
        brands_map = self.get_brands_map()
        loc = config.location
        target_brands = [b.lower() for b in config.filters.brands]
        all_brands = "*" in target_brands or not target_brands

        # Construction des clauses de recherche selon le mode
        queries: List[tuple[str, str, float, float]] = []  # (where_clause, zone_name, center_lat, center_lon)

        if loc.mode == "zones" and loc.zones:
            for z in loc.zones:
                where = f"distance(geom, geom'POINT({z.longitude} {z.latitude})', {z.radius_km}km)"
                queries.append((where, z.name, z.latitude, z.longitude))
        elif loc.mode == "department":
            queries.append((f'code_departement = "{loc.department}"', f"Dpt {loc.department}", loc.latitude, loc.longitude))
        else:
            where = f"distance(geom, geom'POINT({loc.longitude} {loc.latitude})', {loc.radius_km}km)"
            queries.append((where, loc.city or "Secteur", loc.latitude, loc.longitude))

        result = FetchResult(zones_total=len(queries))
        stations_by_id: Dict[int, Station] = {}

        for where_clause, zone_name, c_lat, c_lon in queries:
            records = self._query_ods(where_clause)
            if records is None:
                result.failed_zones.append(zone_name)
                continue
            for rec in records:
                try:
                    sid = int(rec.get("id"))
                except (TypeError, ValueError):
                    continue
                brand = brands_map.get(sid)

                if not all_brands:
                    if not brand or not any(tb in brand.lower() for tb in target_brands):
                        continue

                geom = rec.get("geom") or {}
                lat = geom.get("lat") or 0.0
                lon = geom.get("lon") or 0.0
                dist_km = haversine_distance(c_lat, c_lon, lat, lon)

                # Si déjà vue dans une autre zone, ne garder que si distance plus courte
                if sid in stations_by_id and stations_by_id[sid].distance_km <= dist_km:
                    continue

                automate, hours = _parse_ods_hours(rec.get("horaires"))
                stations_by_id[sid] = build_station(
                    sid, brand or "Station", rec.get("adresse") or "", rec.get("ville") or "",
                    rec.get("cp") or "", lat, lon, dist_km, zone_name,
                    _strip_at(_as_list(rec.get("prix"))), _strip_at(_as_list(rec.get("rupture"))),
                    automate, hours
                )

        result.stations = sorted(stations_by_id.values(), key=lambda s: (s.zone_name, s.distance_km))
        return result

    def fetch_stations(self, config: Config) -> List[Station]:
        return self.fetch(config).stations

class OfficialFeedVerifier:
    """Seconde source indépendante : le flux XML instantané publié par le ministère (roulez-eco.fr).
    Téléchargé uniquement lorsqu'un changement de stock doit être confirmé (~1 Mo compressé)."""
    def __init__(self, url: str = OFFICIAL_FEED_URL):
        self.url = url

    def lookup(self, station_ids: Iterable[int]) -> Optional[Dict[int, Station]]:
        """Retourne l'état des stations demandées selon le flux officiel, ou None s'il est injoignable.
        Une station absente du dictionnaire n'a pas été trouvée dans le flux."""
        try:
            archive = zipfile.ZipFile(io.BytesIO(http_get(self.url, timeout=30)))
            xml = archive.read(archive.namelist()[0]).decode("iso-8859-1")
            if "<pdv " not in xml:
                raise ValueError("flux vide")
        except Exception as e:
            print(f"[!] Flux officiel de recoupement injoignable : {e}")
            return None

        found: Dict[int, Station] = {}
        for sid in station_ids:
            m = re.search(r'<pdv id="%d"[^>]*?(?:/>|>.*?</pdv>)' % int(sid), xml, re.S)
            if not m:
                continue
            try:
                pdv = ET.fromstring(m.group(0))
            except ET.ParseError:
                continue
            horaires = pdv.find("horaires")
            jours = []
            if horaires is not None:
                for j in horaires.findall("jour"):
                    jours.append({**j.attrib, "horaire": [h.attrib for h in j.findall("horaire")]})
            found[int(sid)] = build_station(
                int(sid), "", pdv.findtext("adresse") or "", pdv.findtext("ville") or "", pdv.get("cp") or "",
                0.0, 0.0, 0.0, "",
                [p.attrib for p in pdv.findall("prix")], [r.attrib for r in pdv.findall("rupture")],
                bool(horaires is not None and horaires.get("automate-24-24")), _parse_hours(jours)
            )
        return found
