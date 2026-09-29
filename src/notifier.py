import json
import urllib.request
from typing import Dict, List

from src.tracker import RestockEvent
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
        title = f"⛽ {event.brand} ({event.city} - {event.distance_km} km)"
        lines = [
            f"📍 {event.address} ({event.distance_km} km)",
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

    def send_test_all(self) -> Dict[str, bool]:
        return {self.notifier.name: self.notifier.send_test_message()}
