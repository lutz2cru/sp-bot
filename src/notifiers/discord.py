import json
import urllib.request
from src.notifiers.base import BaseNotifier
from src.tracker import RestockEvent
from src.config import DiscordConfig

class DiscordNotifier(BaseNotifier):
    def __init__(self, config: DiscordConfig):
        self.config = config
        self.webhook_url = config.webhook_url

    @property
    def name(self) -> str:
        return "Discord"

    def _send_payload(self, payload: dict) -> bool:
        if not self.webhook_url:
            print("[!] Webhook Discord non configuré.")
            return False

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SP-Bot/1.0"
        }
        try:
            req = urllib.request.Request(self.webhook_url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            print(f"[!] Erreur d'envoi Discord : {e}")
            return False

    def send_restock_event(self, event: RestockEvent) -> bool:
        restocked_text = "\n".join([
            f"**{f.fuel}** : {f'{f.price:.3f} €/L' if f.price else 'Non précisé'} *({f.relative_time})*"
            for f in event.fuels_restocked
        ])

        fields = [
            {
                "name": "✨ Carburants de nouveau disponibles",
                "value": restocked_text or "Non spécifié",
                "inline": False
            }
        ]

        if event.alternatives:
            fields.append({
                "name": "🔄 Alternatives disponibles",
                "value": ", ".join(event.alternatives),
                "inline": False
            })

        fields.extend([
            {
                "name": "📦 Tous les carburants en stock",
                "value": ", ".join(event.all_available) if event.all_available else "Aucun",
                "inline": False
            },
            {
                "name": "🗺️ Navigation",
                "value": f"[Google Maps]({event.google_maps_url}) • [Waze]({event.waze_url})",
                "inline": False
            }
        ])

        color = 0x2ECC71 if event.status == "DISPONIBLE" else 0xE67E22

        embed = {
            "title": f"⛽ {event.status_badge} : {event.brand}",
            "description": f"📍 **{event.address}**\n{event.postal_code} {event.city} • **{event.distance_km} km**",
            "color": color,
            "fields": fields,
            "footer": {
                "text": "SP-Bot • Modèle de détection Gasoil Now / Essence&CO"
            }
        }
        return self._send_payload({"embeds": [embed]})

    def send_test_message(self) -> bool:
        embed = {
            "title": "✅ SP-Bot : Test Discord réussi !",
            "description": "Le webhook Discord fonctionne correctement et recevra les alertes selon le modèle Gasoil Now.",
            "color": 0x3498DB
        }
        return self._send_payload({"embeds": [embed]})
