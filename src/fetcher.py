import os
import time
import json
import gzip
import csv
import io
import math
import urllib.request
import urllib.parse
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.config import Config

OSM_DATASET_URL = (
    "https://static.data.gouv.fr/resources/"
    "referentiel-des-noms-et-enseignes-de-stations-service-enrichi-par-openstreetmap/"
    "20260927-100009/referentiel-stations-osm.csv"
)

ODS_API_BASE = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance géodésique en km entre deux points GPS (modèle Gasoil Now)."""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)

def format_relative_time(dt_str: str) -> str:
    """Transforme un timestamp ISO ou 'YYYY-MM-DD HH:MM:SS' en durée relative (modèle Essence&CO)."""
    if not dt_str:
        return "Non précisé"
    try:
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(dt_str[:19], fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return dt_str

        now = datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()
        if seconds < 60:
            return "À l'instant"
        minutes = int(seconds // 60)
        if minutes < 60:
            return f"il y a {minutes} min"
        hours = int(minutes // 60)
        if hours < 24:
            return f"il y a {hours}h"
        days = int(hours // 24)
        if days == 1:
            return "hier"
        return f"il y a {days} jours"
    except Exception:
        return dt_str

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
    def __init__(self, data_dir: str = "data"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, data_dir) if not os.path.isabs(data_dir) else data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.cache_path = os.path.join(self.data_dir, "stations_osm_cache.json")
        self._brands_map: Optional[Dict[int, str]] = None

    def get_brands_map(self) -> Dict[int, str]:
        """Charge le référentiel OpenStreetMap des enseignes."""
        if self._brands_map is not None:
            return self._brands_map

        max_age_seconds = 7 * 24 * 3600  # 7 jours
        if os.path.exists(self.cache_path):
            file_age = time.time() - os.path.getmtime(self.cache_path)
            if file_age < max_age_seconds:
                try:
                    with open(self.cache_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._brands_map = {int(k): v for k, v in data.items()}
                        return self._brands_map
                except Exception as e:
                    print(f"[!] Erreur de lecture du cache OSM: {e}")

        brands_map = {}
        try:
            req = urllib.request.Request(OSM_DATASET_URL, headers={"User-Agent": "TotalStationBot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    sid = row.get("id_station_officiel")
                    name = row.get("nom_normalise")
                    if sid and name:
                        try:
                            brands_map[int(sid)] = name
                        except ValueError:
                            pass

            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(brands_map, f, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Impossible de télécharger le référentiel OSM : {e}")
            if os.path.exists(self.cache_path):
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    brands_map = {int(k): v for k, v in json.load(f).items()}

        self._brands_map = brands_map
        return self._brands_map

    def fetch_stations(self, config: Config) -> List[Station]:
        """
        Récupère les stations du secteur et applique la modélisation avancée
        (Gasoil Now / Essence&CO) : statuts tricolores, fraîcheur relative, distance et tri.
        """
        brands_map = self.get_brands_map()

        loc = config.location
        if loc.mode == "department":
            where_clause = f'code_departement = "{loc.department}"'
        else:
            where_clause = f"distance(geom, geom'POINT({loc.longitude} {loc.latitude})', {loc.radius_km}km)"

        target_brands = [b.lower() for b in config.filters.brands]
        is_all_brands = "*" in target_brands or len(target_brands) == 0

        stations = []
        offset = 0
        limit = 100

        while True:
            params = urllib.parse.urlencode({
                "where": where_clause,
                "limit": limit,
                "offset": offset
            })
            url = f"{ODS_API_BASE}?{params}"

            try:
                req = urllib.request.Request(url, headers={"User-Agent": "TotalStationBot/1.0", "Accept-Encoding": "gzip, deflate"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                    if raw[:2] == b"\x1f\x8b" or resp.info().get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    data = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception as e:
                print(f"[!] Erreur API Opendatasoft: {e}")
                break

            results = data.get("results", [])
            total_count = data.get("total_count", 0)

            for rec in results:
                sid = int(rec.get("id", 0))
                brand_name = brands_map.get(sid, "Indépendant / Non répertorié")

                if not is_all_brands:
                    if not any(tb in brand_name.lower() for tb in target_brands):
                        continue

                # Coordonnées GPS
                geom = rec.get("geom", {})
                lat = geom.get("lat")
                lon = geom.get("lon")
                if lat is None or lon is None:
                    try:
                        lat = float(rec.get("latitude", 0)) / 100000.0
                        lon = float(rec.get("longitude", 0)) / 100000.0
                    except (ValueError, TypeError):
                        lat, lon = 0.0, 0.0

                # Calcul de distance exacte (comme Gasoil Now)
                dist_km = haversine_distance(loc.latitude, loc.longitude, lat, lon)

                # Carburants disponibles et ruptures
                dispos = rec.get("carburants_disponibles") or []
                if isinstance(dispos, str):
                    dispos = [x.strip() for x in dispos.split(";") if x.strip()]

                rupt_temp = rec.get("carburants_rupture_temporaire") or []
                if isinstance(rupt_temp, str):
                    rupt_temp = [x.strip() for x in rupt_temp.split(";") if x.strip()]

                rupt_def = rec.get("carburants_rupture_definitive") or []
                if isinstance(rupt_def, str):
                    rupt_def = [x.strip() for x in rupt_def.split(";") if x.strip()]

                # Extraction des prix et fraîcheur temporelle
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
                            p_nom = p.get("@nom")
                            p_val = p.get("@valeur")
                            p_maj = p.get("@maj")
                            if p_nom and p_val:
                                try:
                                    prices_dict[p_nom] = {
                                        "valeur": float(p_val),
                                        "maj": p_maj or "",
                                        "relative_time": format_relative_time(p_maj or "")
                                    }
                                except ValueError:
                                    pass

                # Classification 3 statuts (Modèle Gasoil Now / Essence&CO)
                if not dispos:
                    status = "RUPTURE_TOTALE"
                elif rupt_temp:
                    status = "RUPTURE_PARTIELLE"
                else:
                    status = "DISPONIBLE"

                maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                waze_url = f"https://waze.com/ul?ll={lat},{lon}&navigate=yes"

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
                    google_maps_url=maps_url,
                    waze_url=waze_url
                ))

            offset += len(results)
            if offset >= total_count or len(results) == 0:
                break

        # Tri par distance croissante (Gasoil Now)
        stations.sort(key=lambda s: s.distance_km)
        return stations
