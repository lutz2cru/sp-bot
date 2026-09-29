import json
import os
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ZoneConfig:
    name: str
    latitude: float
    longitude: float
    radius_km: int

@dataclass
class LocationConfig:
    mode: str = "zones"  # "zones", "gps", "city", ou "department"
    latitude: float = 47.6397
    longitude: float = 6.8638
    radius_km: int = 20
    city: str = "Belfort"
    department: str = "90"
    zones: List[ZoneConfig] = field(default_factory=lambda: [
        ZoneConfig(name="Belfort", latitude=47.6397, longitude=6.8638, radius_km=12),
        ZoneConfig(name="Montbéliard", latitude=47.5100, longitude=6.7980, radius_km=10),
        ZoneConfig(name="Lure (Axe N19)", latitude=47.6833, longitude=6.4917, radius_km=15),
        ZoneConfig(name="Vesoul", latitude=47.6239, longitude=6.1555, radius_km=12)
    ])

@dataclass
class FiltersConfig:
    brands: List[str] = field(default_factory=lambda: ["Total", "Total Access", "TotalEnergies"])
    fuels: List[str] = field(default_factory=lambda: ["Gazole", "SP95", "E10", "SP98", "E85", "GPLc"])

@dataclass
class NtfyConfig:
    enabled: bool = True
    topic: str = "sp-bot-alerte-total-belfort"
    server: str = "https://ntfy.sh"
    priority: int = 4

@dataclass
class Config:
    location: LocationConfig = field(default_factory=LocationConfig)
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    ntfy: NtfyConfig = field(default_factory=NtfyConfig)
    check_interval_seconds: int = 300
    notify_on_startup: bool = False

def geocode_city_gouv(city_name: str) -> Optional[tuple[float, float, str]]:
    """Résout une commune en coordonnées GPS via l'API officielle api-adresse.data.gouv.fr."""
    try:
        params = urllib.parse.urlencode({'q': city_name, 'limit': 1})
        url = f"https://api-adresse.data.gouv.fr/search/?{params}"
        req = urllib.request.Request(url, headers={'User-Agent': 'SPBot/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            features = data.get('features', [])
            if features:
                coords = features[0]['geometry']['coordinates']
                return float(coords[1]), float(coords[0]), features[0]['properties']['label']
    except Exception as e:
        print(f"[!] Erreur géocodage '{city_name}': {e}")
    return None

def load_config(config_path: str = "config.json") -> Config:
    """Charge la configuration depuis config.json ou l'environnement Cloud."""
    if not os.path.isabs(config_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, config_path)

    data = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[!] Erreur lecture {config_path}: {e}")

    loc_data = data.get("location", {})
    raw_zones = loc_data.get("zones", [])
    zones_list = []
    if raw_zones:
        for z in raw_zones:
            zones_list.append(ZoneConfig(
                name=z.get("name", "Zone"),
                latitude=float(z.get("latitude", 0.0)),
                longitude=float(z.get("longitude", 0.0)),
                radius_km=int(z.get("radius_km", 10))
            ))
    else:
        # Zones par défaut : Belfort, Montbéliard, Lure (Axe N19), Vesoul
        zones_list = [
            ZoneConfig(name="Belfort", latitude=47.6397, longitude=6.8638, radius_km=12),
            ZoneConfig(name="Montbéliard", latitude=47.5100, longitude=6.7980, radius_km=10),
            ZoneConfig(name="Lure (Axe N19)", latitude=47.6833, longitude=6.4917, radius_km=15),
            ZoneConfig(name="Vesoul", latitude=47.6239, longitude=6.1555, radius_km=12)
        ]

    loc = LocationConfig(
        mode=loc_data.get("mode", "zones"),
        latitude=float(loc_data.get("latitude", 47.6397)),
        longitude=float(loc_data.get("longitude", 6.8638)),
        radius_km=int(loc_data.get("radius_km", 20)),
        city=loc_data.get("city", "Belfort"),
        department=str(loc_data.get("department", "90")),
        zones=zones_list
    )

    filt_data = data.get("filters", {})
    filters = FiltersConfig(
        brands=filt_data.get("brands", ["Total", "Total Access", "TotalEnergies"]),
        fuels=filt_data.get("fuels", ["Gazole", "SP95", "E10", "SP98", "E85", "GPLc"])
    )

    ntfy_data = data.get("ntfy", {})
    ntfy_topic = os.environ.get("NTFY_TOPIC") or ntfy_data.get("topic", "sp-bot-alerte-total-belfort")
    ntfy = NtfyConfig(
        enabled=True,
        topic=ntfy_topic,
        server=ntfy_data.get("server", "https://ntfy.sh"),
        priority=int(ntfy_data.get("priority", 4))
    )

    return Config(
        location=loc,
        filters=filters,
        ntfy=ntfy,
        check_interval_seconds=int(os.environ.get("CHECK_INTERVAL", data.get("check_interval_seconds", 300))),
        notify_on_startup=bool(data.get("notify_on_startup", False))
    )

def save_config(config: Config, config_path: str = "config.json") -> None:
    data = {
        "location": {
            "mode": config.location.mode,
            "latitude": config.location.latitude,
            "longitude": config.location.longitude,
            "radius_km": config.location.radius_km,
            "city": config.location.city,
            "department": config.location.department,
            "zones": [
                {
                    "name": z.name,
                    "latitude": z.latitude,
                    "longitude": z.longitude,
                    "radius_km": z.radius_km
                }
                for z in config.location.zones
            ]
        },
        "filters": {
            "brands": config.filters.brands,
            "fuels": config.filters.fuels
        },
        "ntfy": {
            "topic": config.ntfy.topic,
            "server": config.ntfy.server,
            "priority": config.ntfy.priority
        },
        "check_interval_seconds": config.check_interval_seconds,
        "notify_on_startup": config.notify_on_startup
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
