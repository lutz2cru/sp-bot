import os
import json
import gzip
import math
import urllib.request
import urllib.parse
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from src.config import Config, ZoneConfig

ODS_API_BASE = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
FIELDS_SELECT = "id,adresse,ville,cp,geom,prix,carburants_disponibles,carburants_rupture_temporaire,carburants_rupture_definitive"

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance géodésique rapide en km entre deux points GPS (modèle Gasoil Now)."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return round(R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)), 1)

def format_relative_time(dt_str: str) -> str:
    """Calcul de fraîcheur relative ultra-léger (modèle Essence&CO)."""
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
        diff = (datetime.now() - dt).total_seconds()
        if diff < 60:
            return "à l'instant"
        mins = int(diff // 60)
        if mins < 60:
            return f"il y a {mins} min"
        hours = int(mins // 60)
        if hours < 24:
            return f"il y a {hours}h"
        days = int(hours // 24)
        return "hier" if days == 1 else f"il y a {days}j"
    except Exception:
        return ""

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

    def _query_ods(self, where_clause: str) -> List[dict]:
        params = urllib.parse.urlencode({
            "where": where_clause,
            "select": FIELDS_SELECT,
            "limit": 100
        })
        url = f"{ODS_API_BASE}?{params}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SP-Bot/1.0", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8")).get("results", [])
        except Exception as e:
            print(f"[!] Erreur API ODS: {e}")
            return []

    def fetch_stations(self, config: Config) -> List[Station]:
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

        stations_by_id: Dict[int, Station] = {}

        for where_clause, zone_name, c_lat, c_lon in queries:
            results = self._query_ods(where_clause)
            for rec in results:
                sid = int(rec.get("id", 0))
                brand = brands_map.get(sid)

                if not all_brands:
                    if not brand or not any(tb in brand.lower() for tb in target_brands):
                        continue
                brand_name = brand or "Station"

                geom = rec.get("geom") or {}
                lat = geom.get("lat") or 0.0
                lon = geom.get("lon") or 0.0
                dist_km = haversine_distance(c_lat, c_lon, lat, lon)

                # Si déjà vue dans une autre zone, ne garder que si distance plus courte
                if sid in stations_by_id and stations_by_id[sid].distance_km <= dist_km:
                    continue

                dispos = rec.get("carburants_disponibles") or []
                if isinstance(dispos, str):
                    dispos = [x.strip() for x in dispos.split(";") if x.strip()]

                rupt_temp = rec.get("carburants_rupture_temporaire") or []
                if isinstance(rupt_temp, str):
                    rupt_temp = [x.strip() for x in rupt_temp.split(";") if x.strip()]

                rupt_def = rec.get("carburants_rupture_definitive") or []
                if isinstance(rupt_def, str):
                    rupt_def = [x.strip() for x in rupt_def.split(";") if x.strip()]

                prices_dict = {}
                raw_prix = rec.get("prix")
                if isinstance(raw_prix, str):
                    try:
                        raw_prix = json.loads(raw_prix)
                    except Exception:
                        raw_prix = []
                if isinstance(raw_prix, list):
                    for p in raw_prix:
                        if isinstance(p, dict):
                            p_nom, p_val, p_maj = p.get("@nom"), p.get("@valeur"), p.get("@maj")
                            if p_nom and p_val:
                                try:
                                    prices_dict[p_nom] = {
                                        "valeur": float(p_val),
                                        "maj": p_maj or "",
                                        "relative_time": format_relative_time(p_maj or "")
                                    }
                                except ValueError:
                                    pass

                status = "RUPTURE_TOTALE" if not dispos else ("RUPTURE_PARTIELLE" if rupt_temp else "DISPONIBLE")

                stations_by_id[sid] = Station(
                    id=sid,
                    brand=brand_name,
                    address=rec.get("adresse", ""),
                    city=rec.get("ville", ""),
                    postal_code=rec.get("cp", ""),
                    latitude=lat,
                    longitude=lon,
                    distance_km=dist_km,
                    zone_name=zone_name,
                    status=status,
                    disponibles=dispos,
                    rupture_temporaire=rupt_temp,
                    rupture_definitive=rupt_def,
                    prices=prices_dict,
                    google_maps_url=f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                    waze_url=f"https://waze.com/ul?ll={lat},{lon}&navigate=yes"
                )

        station_list = list(stations_by_id.values())
        station_list.sort(key=lambda s: (s.zone_name, s.distance_km))
        return station_list
