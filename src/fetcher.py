import os
import json
import gzip
import math
import urllib.request
import urllib.parse
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from src.config import Config

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
    status: str  # "DISPONIBLE", "RUPTURE_PARTIELLE", "RUPTURE_TOTALE"
    disponibles: List[str]
    rupture_temporaire: List[str]
    rupture_definitive: List[str]
    prices: Dict[str, Dict[str, Any]]
    google_maps_url: str
    waze_url: str

class FuelFetcher:
    """Récupérateur haute performance et basse consommation de données carburant."""
    def __init__(self, data_dir: str = "data"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, data_dir) if not os.path.isabs(data_dir) else data_dir
        self.stations_bundle = os.path.join(self.data_dir, "total_stations.json")
        self._brands_cache: Optional[Dict[int, str]] = None

    def get_brands_map(self) -> Dict[int, str]:
        """Charge le dictionnaire pré-embarqué des 2327 stations Total en France (55 Ko, chargement instantané)."""
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

    def fetch_stations(self, config: Config) -> List[Station]:
        """Interroge l'API officielle avec un payload minimal (~3 Ko) et traite les statuts."""
        brands_map = self.get_brands_map()
        loc = config.location

        if loc.mode == "department":
            where_clause = f'code_departement = "{loc.department}"'
        else:
            where_clause = f"distance(geom, geom'POINT({loc.longitude} {loc.latitude})', {loc.radius_km}km)"

        # Requête optimisée avec select=... (ignore horaires, services, etc.)
        params = urllib.parse.urlencode({
            "where": where_clause,
            "select": FIELDS_SELECT,
            "limit": 100
        })
        url = f"{ODS_API_BASE}?{params}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "SP-Bot/1.0", "Accept-Encoding": "gzip"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            print(f"[!] Erreur requête API: {e}")
            return []

        stations = []
        target_brands = [b.lower() for b in config.filters.brands]
        all_brands = "*" in target_brands or not target_brands

        for rec in data.get("results", []):
            sid = int(rec.get("id", 0))
            brand = brands_map.get(sid)

            # Filtrage des enseignes
            if not all_brands:
                if not brand or not any(tb in brand.lower() for tb in target_brands):
                    continue
            brand_name = brand or "Station"

            # Coordonnées géographiques
            geom = rec.get("geom") or {}
            lat = geom.get("lat") or 0.0
            lon = geom.get("lon") or 0.0
            dist_km = haversine_distance(loc.latitude, loc.longitude, lat, lon)

            # Traitement carburants
            dispos = rec.get("carburants_disponibles") or []
            if isinstance(dispos, str):
                dispos = [x.strip() for x in dispos.split(";") if x.strip()]

            rupt_temp = rec.get("carburants_rupture_temporaire") or []
            if isinstance(rupt_temp, str):
                rupt_temp = [x.strip() for x in rupt_temp.split(";") if x.strip()]

            rupt_def = rec.get("carburants_rupture_definitive") or []
            if isinstance(rupt_def, str):
                rupt_def = [x.strip() for x in rupt_def.split(";") if x.strip()]

            # Traitement des prix
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

            # Statuts Gasoil Now / Essence&CO
            if not dispos:
                status = "RUPTURE_TOTALE"
            elif rupt_temp:
                status = "RUPTURE_PARTIELLE"
            else:
                status = "DISPONIBLE"

            stations.append(Station(
                id=sid,
                brand=brand_name,
                address=rec.get("adresse", ""),
                city=rec.get("ville", ""),
                postal_code=rec.get("cp", ""),
                latitude=lat,
                longitude=lon,
                distance_km=dist_km,
                status=status,
                disponibles=dispos,
                rupture_temporaire=rupt_temp,
                rupture_definitive=rupt_def,
                prices=prices_dict,
                google_maps_url=f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                waze_url=f"https://waze.com/ul?ll={lat},{lon}&navigate=yes"
            ))

        stations.sort(key=lambda s: s.distance_km)
        return stations
