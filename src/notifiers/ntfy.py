import json
import urllib.request
from typing import Optional

from src.notifiers.base import BaseNotifier
from src.tracker import RestockEvent
from src.config import NtfyConfig

class NtfyNotifier(BaseNotifier):
    def __init__(self, config: NtfyConfig):
        self.config = config
        self.server = config.server.rstrip("/")
        self.topic = config.topic

    @property
    def name(self) -> str:
        return "Ntfy (Push Mobile)"

    def _post_json(self, payload: dict) -> bool:
        url = f"{self.server}"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SP-Bot/1.0"
        }
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            print(f"[!] Erreur d'envoi Ntfy : {e}")
            return False

    def send_restock_event(self, event: RestockEvent) -> bool:
        title = f"⛽ Réapprovisionnement : {event.brand} ({event.city} - {event.distance_km} km)"

        lines = [
            f"📍 {event.address}, {event.postal_code} {event.city} ({event.distance_km} km)",
            f"📊 Statut : {event.status_badge}",
            "",
            "✨ Carburants de nouveau en stock :"
        ]
        for f in event.fuels_restocked:
            price_str = f"{f.price:.3f} €/L" if f.price else "Prix non précisé"
            time_str = f"({f.relative_time})" if f.relative_time else ""
            lines.append(f"  • {f.fuel} : {price_str} {time_str}".strip())

        if event.alternatives:
            lines.append("")
            lines.append(f"🔄 Alternatives disponibles : {', '.join(event.alternatives)}")

        lines.append("")
        lines.append(f"📦 Tous les carburants disponibles : {', '.join(event.all_available)}")

        payload = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(lines),
            "priority": self.config.priority,
            "tags": ["fuelpump", "white_check_mark", "round_pushpin"],
            "click": event.google_maps_url,
            "actions": [
                {
                    "action": "view",
                    "label": "Google Maps",
                    "url": event.google_maps_url
                },
                {
                    "action": "view",
                    "label": "Waze",
                    "url": event.waze_url
                }
            ]
        }
        return self._post_json(payload)

    def send_test_message(self) -> bool:
        payload = {
            "topic": self.topic,
            "title": "✅ SP-Bot : Test de notification réussi !",
            "message": "Votre téléphone est correctement configuré (modèle Gasoil Now / Essence&CO) pour recevoir les alertes de réapprovisionnement.",
            "priority": 3,
            "tags": ["tada", "fuelpump"]
        }
        return self._post_json(payload)
