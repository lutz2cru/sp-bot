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

@dataclass
class RestockedFuel:
    fuel: str
    price: Optional[float]
    maj: str
    relative_time: str

@dataclass
class RestockEvent:
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

    def process_stations(self, stations: List[Station], config: Config) -> List[RestockEvent]:
        """
        Compare l'état actuel et précédent en appliquant les heuristiques de détection
        avancées de Gasoil Now et Essence&CO (transition de statut, horodatage frais, alternatives).
        """
        old_state = self.load_state()
        old_stations = old_state.get("stations", {})
        is_initialized = old_state.get("initialized", False)

        events: List[RestockEvent] = []
        new_stations_state: Dict[str, Any] = {}
        target_fuels = [f.lower() for f in config.filters.fuels]

        for s in stations:
            sid_str = str(s.id)
            prev = old_stations.get(sid_str)

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

            for fuel_name in s.disponibles:
                if fuel_name.lower() not in target_fuels:
                    continue

                price_info = s.prices.get(fuel_name, {})
                price_val = price_info.get("valeur")
                price_maj = price_info.get("maj", "")
                rel_time = price_info.get("relative_time", "À l'instant")

                if prev is None:
                    if is_initialized:
                        restocked_fuels.append(RestockedFuel(
                            fuel=fuel_name,
                            price=price_val,
                            maj=price_maj,
                            relative_time=rel_time
                        ))
                else:
                    prev_dispos = prev.get("disponibles", [])
                    prev_rupt_temp = prev.get("rupture_temporaire", [])
                    prev_status = prev.get("status", "")
                    prev_prices = prev.get("prices", {})
                    prev_fuel_info = prev_prices.get(fuel_name, {})
                    prev_maj = prev_fuel_info.get("maj", "")

                    # 1. Était en rupture temporaire et n'y est plus
                    was_in_rupture = any(r.lower() == fuel_name.lower() for r in prev_rupt_temp)
                    # 2. Était absent des disponibles
                    was_unavailable = not any(d.lower() == fuel_name.lower() for d in prev_dispos)
                    # 3. La station était en rupture totale
                    was_total_shortage = prev_status == "RUPTURE_TOTALE"
                    # 4. Nouveau prix ou horodatage maj mis à jour (livraison par camion)
                    has_fresh_update = price_maj and price_maj != prev_maj and (was_in_rupture or was_unavailable or was_total_shortage)

                    if was_in_rupture or was_unavailable or has_fresh_update:
                        restocked_fuels.append(RestockedFuel(
                            fuel=fuel_name,
                            price=price_val,
                            maj=price_maj,
                            relative_time=rel_time
                        ))

            if restocked_fuels:
                badge = "🟢 DISPONIBLE" if s.status == "DISPONIBLE" else "🟠 RUPTURE PARTIELLE"

                # Détection d'alternatives disponibles (Essence&CO style)
                alternatives = []
                for rf in restocked_fuels:
                    alts = FUEL_ALTERNATIVES.get(rf.fuel.lower(), [])
                    for alt in alts:
                        if alt.lower() != rf.fuel.lower() and alt in s.disponibles:
                            p = s.prices.get(alt, {}).get("valeur")
                            p_str = f" ({p:.3f} €/L)" if p else ""
                            alt_entry = f"{alt}{p_str}"
                            if alt_entry not in alternatives:
                                alternatives.append(alt_entry)

                events.append(RestockEvent(
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
                    waze_url=s.waze_url
                ))

        self.save_state({
            "initialized": True,
            "last_check": datetime.now().isoformat(),
            "stations": new_stations_state
        })

        return events
