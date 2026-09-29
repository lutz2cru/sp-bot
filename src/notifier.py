import json
import urllib.request
from typing import Dict, List, Tuple

from src.tracker import RestockEvent, normalize_fuel
from src.fetcher import Station
from src.config import NtfyConfig

class NtfyNotifier:
    """Notificateur push mobile instantané via Ntfy.sh (0 compte, 0 mot de passe, ultra-sobre)."""
    def __init__(self, config: NtfyConfig):
        self.config = config
        self.server = config.server.rstrip("/")
        self.topic = config.topic

    @property
    def name(self) -> str:
        return f"Ntfy (topic: {self.topic})"

    def _post(self, payload: dict) -> bool:
        url = self.server
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SP-Bot/1.0"
        }
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            print(f"[!] Erreur Ntfy : {e}")
            return False

    def send_restock_event(self, event: RestockEvent) -> bool:
        title = f"⛽ [{event.zone_name}] {event.brand} ({event.city} - {event.distance_km} km)"
        lines = [
            f"📍 {event.address}, {event.postal_code} {event.city} ({event.distance_km} km)",
            f"Statut : {event.status_badge}",
            "",
            "✨ Carburants de nouveau en stock :"
        ]
        for f in event.fuels_restocked:
            p_str = f"{f.price:.3f} €/L" if f.price else "Prix non précisé"
            rel_str = f"({f.relative_time})" if f.relative_time else ""
            lines.append(f"  • {f.fuel} : {p_str} {rel_str}".strip())

        if event.alternatives:
            lines.append(f"\n🔄 Alternatives disponibles : {', '.join(event.alternatives)}")

        payload = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(lines),
            "priority": self.config.priority,
            "tags": ["fuelpump", "white_check_mark", "round_pushpin"],
            "click": event.google_maps_url,
            "actions": [
                {"action": "view", "label": "Google Maps", "url": event.google_maps_url},
                {"action": "view", "label": "Waze", "url": event.waze_url}
            ]
        }
        return self._post(payload)

    def send_stock_list(self, stations: List[Station], target_fuels: List[str]) -> bool:
        """Envoie la liste en direct de toutes les stations Total ayant les carburants ciblés en stock."""
        norm_targets = [normalize_fuel(tf) for tf in target_fuels]
        available_stations: List[Tuple[Station, List[str]]] = []

        for s in stations:
            matched_fuels = [f for f in s.disponibles if normalize_fuel(f) in norm_targets]
            if matched_fuels:
                available_stations.append((s, matched_fuels))

        if available_stations:
            fuel_label = " / ".join(target_fuels)
            title = f"⛽ Total {fuel_label} : {len(available_stations)} station(s) en stock"
            lines = [f"🟢 STATIONS AVEC {fuel_label.upper()} EN STOCK :\n"]

            for s, fuels in available_stations:
                fuel_strs = []
                for f in fuels:
                    p = s.prices.get(f, {})
                    val_str = f"{p.get('valeur'):.3f} €/L" if p.get('valeur') else "Prix dispo"
                    time_str = f"({p.get('relative_time')})" if p.get('relative_time') else ""
                    fuel_strs.append(f"{f}: {val_str} {time_str}".strip())

                lines.append(f"• [{s.zone_name}] {s.brand} ({s.distance_km} km)")
                lines.append(f"  📍 {s.address}, {s.city}")
                lines.append(f"  👉 {' | '.join(fuel_strs)}\n")

            rupture_count = len(stations) - len(available_stations)
            if rupture_count > 0:
                lines.append(f"🔴 {rupture_count} autre(s) station(s) Total en rupture dans le secteur.")

            # Liens d'action vers les stations disponibles (max 3 actions autorisées par Ntfy)
            actions = []
            first_station = available_stations[0][0]
            actions.append({"action": "view", "label": f"Maps {first_station.city}", "url": first_station.google_maps_url})
            actions.append({"action": "view", "label": f"Waze {first_station.city}", "url": first_station.waze_url})
            if len(available_stations) > 1:
                second_station = available_stations[1][0]
                actions.append({"action": "view", "label": f"Maps {second_station.city}", "url": second_station.google_maps_url})

            click_url = first_station.google_maps_url
            tags = ["fuelpump", "white_check_mark"]
        else:
            fuel_label = " / ".join(target_fuels)
            title = f"⚠️ Pénurie : 0 station Total avec {fuel_label}"
            lines = [
                f"🔴 Aucune des {len(stations)} stations Total surveillées (Belfort, Montbéliard, Lure, Vesoul) n'a de {fuel_label} en stock actuellement."
            ]
            actions = []
            click_url = "https://maps.google.com"
            tags = ["fuelpump", "warning"]

        payload = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(lines).strip(),
            "priority": self.config.priority,
            "tags": tags,
            "click": click_url,
        }
        if actions:
            payload["actions"] = actions[:3]
        return self._post(payload)

    def send_test_message(self) -> bool:
        payload = {
            "topic": self.topic,
            "title": "✅ SP-Bot : Test notification réussi !",
            "message": f"Votre téléphone est connecté au canal '{self.topic}'. Les alertes de réapprovisionnement arriveront ici 24h/24.",
            "priority": 3,
            "tags": ["tada", "fuelpump"]
        }
        return self._post(payload)


class NotificationManager:
    """Gestionnaire d'alerte centré exclusivement sur Ntfy."""
    def __init__(self, config):
        self.notifier = NtfyNotifier(config.ntfy)

    @property
    def active_channels(self) -> List[str]:
        return [self.notifier.name]

    def broadcast_restock(self, event: RestockEvent) -> int:
        return 1 if self.notifier.send_restock_event(event) else 0

    def broadcast_stock_list(self, stations: List[Station], target_fuels: List[str]) -> bool:
        return self.notifier.send_stock_list(stations, target_fuels)

    def send_test_all(self) -> Dict[str, bool]:
        return {self.notifier.name: self.notifier.send_test_message()}
