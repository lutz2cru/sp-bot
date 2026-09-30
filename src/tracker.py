import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.fetcher import Station
from src.config import Config

# Groupes de compatibilité pour les alternatives (modèle Essence&CO)
FUEL_ALTERNATIVES = {
    "gazole": ["Gazole"],
    "sp95": ["E10", "SP98"],
    "e10": ["SP95", "SP98"],
    "sp98": ["SP95", "E10"],
    "e85": ["E85"],
    "gplc": ["GPLc"]
}

def normalize_fuel(name: str) -> str:
    """Normalise les noms de carburants (ex: 'SP95-E10', 'E10', 'Diesel' -> 'e10', 'gazole')."""
    n = name.strip().lower().replace("-", "").replace(" ", "")
    if "e10" in n:
        return "e10"
    if "95" in n:
        return "sp95"
    if "98" in n:
        return "sp98"
    if "gazole" in n or "diesel" in n:
        return "gazole"
    if "e85" in n or "ethanol" in n:
        return "e85"
    if "gpl" in n:
        return "gplc"
    return n

@dataclass
class RestockedFuel:
    fuel: str
    price: Optional[float]
    maj: str
    relative_time: str

@dataclass
class StockChangeEvent:
    station_id: int
    brand: str
    address: str
    city: str
    postal_code: str
    latitude: float
    longitude: float
    distance_km: float
    zone_name: str
    status: str
    status_badge: str
    fuels_restocked: List[RestockedFuel]
    all_available: List[str]
    alternatives: List[str]
    google_maps_url: str
    waze_url: str
    event_type: str = "RESTOCK"  # "RESTOCK" (disponible) ou "SHORTAGE" (rupture)
    fuels_affected: List[str] = field(default_factory=list)

# Alias pour rétrocompatibilité
RestockEvent = StockChangeEvent

class FuelTracker:
    def __init__(self, data_dir: str = "data"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, data_dir) if not os.path.isabs(data_dir) else data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.state_file = os.path.join(self.data_dir, "state.json")

    def load_state(self) -> Dict[str, Any]:
        """Charge l'état précédent des stations."""
        if not os.path.exists(self.state_file):
            return {"initialized": False, "stations": {}}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Erreur de lecture de state.json : {e}")
            return {"initialized": False, "stations": {}}

    def save_state(self, state: Dict[str, Any]) -> None:
        """Sauvegarde l'état actuel des stations."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Erreur d'écriture de state.json : {e}")

    def process_stations(self, stations: List[Station], config: Config) -> List[StockChangeEvent]:
        """
        Compare l'état actuel et précédent en détectant :
        1. Les réapprovisionnements (RESTOCK) : un carburant ciblé redevient disponible.
        2. Les ruptures (SHORTAGE) : un carburant ciblé tombe en rupture de stock.
        """
        old_state = self.load_state()
        old_stations = old_state.get("stations", {})
        is_initialized = old_state.get("initialized", False)

        events: List[StockChangeEvent] = []
        new_stations_state: Dict[str, Any] = {}
        target_fuels = [normalize_fuel(f) for f in config.filters.fuels]

        for s in stations:
            sid_str = str(s.id)
            prev = old_stations.get(sid_str)

            # Protection Anti-Cache Obsolète (Désynchronisation entre nœuds API Opendatasoft)
            # Si un nœud de cache renvoie un horodatage antérieur à ce qu'on a déjà validé,
            # on ignore ce snapshot périmé pour éviter les fausses ruptures/réapprovisionnements (flapping).
            if prev:
                prev_prices = prev.get("prices", {})
                prev_latest_maj = max((p.get("maj", "") for p in prev_prices.values() if p.get("maj")), default="")
                curr_latest_maj = max((p.get("maj", "") for p in s.prices.values() if p.get("maj")), default="")
                if prev_latest_maj and curr_latest_maj and curr_latest_maj < prev_latest_maj:
                    new_stations_state[sid_str] = prev
                    continue

            # Enregistrement de l'état actuel
            new_stations_state[sid_str] = {
                "brand": s.brand,
                "city": s.city,
                "address": s.address,
                "status": s.status,
                "distance_km": s.distance_km,
                "disponibles": s.disponibles,
                "rupture_temporaire": s.rupture_temporaire,
                "rupture_definitive": s.rupture_definitive,
                "prices": s.prices,
                "last_seen": datetime.now().isoformat()
            }

            if not is_initialized and not config.notify_on_startup:
                continue

            restocked_fuels: List[RestockedFuel] = []
            shortage_fuels: List[str] = []

            if prev is None:
                if is_initialized:
                    for fuel_name in s.disponibles:
                        if normalize_fuel(fuel_name) in target_fuels:
                            price_info = s.prices.get(fuel_name, {})
                            restocked_fuels.append(RestockedFuel(
                                fuel=fuel_name,
                                price=price_info.get("valeur"),
                                maj=price_info.get("maj", ""),
                                relative_time=price_info.get("relative_time", "À l'instant")
                            ))
            else:
                prev_dispos = prev.get("disponibles", [])
                prev_status = prev.get("status", "")
                prev_prices = prev.get("prices", {})

                for f_norm in target_fuels:
                    prev_matching = [d for d in prev_dispos if normalize_fuel(d) == f_norm]
                    was_avail = len(prev_matching) > 0

                    curr_matching = [d for d in s.disponibles if normalize_fuel(d) == f_norm]
                    is_avail = len(curr_matching) > 0

                    # Cas 1 : Réapprovisionnement (n'était pas dispo -> est dispo maintenant)
                    if not was_avail and is_avail:
                        for fuel_name in curr_matching:
                            price_info = s.prices.get(fuel_name, {})
                            restocked_fuels.append(RestockedFuel(
                                fuel=fuel_name,
                                price=price_info.get("valeur"),
                                maj=price_info.get("maj", ""),
                                relative_time=price_info.get("relative_time", "À l'instant")
                            ))

                    # Cas 2 : Rupture (était dispo -> n'est plus dispo)
                    elif was_avail and not is_avail:
                        for fuel_name in prev_matching:
                            if fuel_name not in shortage_fuels:
                                shortage_fuels.append(fuel_name)

                    # Cas 3 : Déjà dispo, mais nouvelle livraison confirmée par nouveau prix après rupture totale
                    elif was_avail and is_avail:
                        for fuel_name in curr_matching:
                            price_info = s.prices.get(fuel_name, {})
                            price_maj = price_info.get("maj", "")
                            prev_maj = prev_prices.get(fuel_name, {}).get("maj", "")
                            was_total_shortage = prev_status == "RUPTURE_TOTALE"
                            if price_maj and price_maj != prev_maj and was_total_shortage:
                                restocked_fuels.append(RestockedFuel(
                                    fuel=fuel_name,
                                    price=price_info.get("valeur"),
                                    maj=price_maj,
                                    relative_time=price_info.get("relative_time", "À l'instant")
                                ))

            # Événement RESTOCK (disponible)
            if restocked_fuels:
                badge = "🟢 DISPONIBLE" if s.status == "DISPONIBLE" else "🟠 RUPTURE PARTIELLE"
                alternatives = []
                for rf in restocked_fuels:
                    alts = FUEL_ALTERNATIVES.get(normalize_fuel(rf.fuel), [])
                    for alt in alts:
                        if alt.lower() != rf.fuel.lower() and alt in s.disponibles:
                            p = s.prices.get(alt, {}).get("valeur")
                            p_str = f" ({p:.3f} €/L)" if p else ""
                            alt_entry = f"{alt}{p_str}"
                            if alt_entry not in alternatives:
                                alternatives.append(alt_entry)

                events.append(StockChangeEvent(
                    station_id=s.id,
                    brand=s.brand,
                    address=s.address,
                    city=s.city,
                    postal_code=s.postal_code,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    distance_km=s.distance_km,
                    zone_name=s.zone_name,
                    status=s.status,
                    status_badge=badge,
                    fuels_restocked=restocked_fuels,
                    all_available=s.disponibles,
                    alternatives=alternatives,
                    google_maps_url=s.google_maps_url,
                    waze_url=s.waze_url,
                    event_type="RESTOCK",
                    fuels_affected=[rf.fuel for rf in restocked_fuels]
                ))

            # Événement SHORTAGE (rupture)
            if shortage_fuels:
                badge = "🔴 RUPTURE" if not s.disponibles else ("🔴 RUPTURE TOTALE" if s.status == "RUPTURE_TOTALE" else "🟠 RUPTURE PARTIELLE")
                remaining_alts = []
                for sf in shortage_fuels:
                    alts = FUEL_ALTERNATIVES.get(normalize_fuel(sf), [])
                    for alt in alts:
                        if alt.lower() != sf.lower() and alt in s.disponibles:
                            p = s.prices.get(alt, {}).get("valeur")
                            p_str = f" ({p:.3f} €/L)" if p else ""
                            alt_entry = f"{alt}{p_str}"
                            if alt_entry not in remaining_alts:
                                remaining_alts.append(alt_entry)

                events.append(StockChangeEvent(
                    station_id=s.id,
                    brand=s.brand,
                    address=s.address,
                    city=s.city,
                    postal_code=s.postal_code,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    distance_km=s.distance_km,
                    zone_name=s.zone_name,
                    status=s.status,
                    status_badge=badge,
                    fuels_restocked=[],
                    all_available=s.disponibles,
                    alternatives=remaining_alts,
                    google_maps_url=s.google_maps_url,
                    waze_url=s.waze_url,
                    event_type="SHORTAGE",
                    fuels_affected=shortage_fuels
                ))

        self.save_state({
            "initialized": True,
            "last_check": datetime.now().isoformat(),
            "stations": new_stations_state
        })

        return events
