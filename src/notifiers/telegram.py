import json
import urllib.request
from src.notifiers.base import BaseNotifier
from src.tracker import RestockEvent
from src.config import TelegramConfig

class TelegramNotifier(BaseNotifier):
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.token = config.bot_token
        self.chat_id = config.chat_id

    @property
    def name(self) -> str:
        return "Telegram"

    def _send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            print("[!] Token ou Chat ID Telegram non configuré.")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("ok", False)
        except Exception as e:
            print(f"[!] Erreur d'envoi Telegram : {e}")
            return False

    def send_restock_event(self, event: RestockEvent) -> bool:
        text = (
            f"⛽ <b>RÉAPPROVISIONNEMENT DÉTECTÉ !</b>\n"
            f"📊 Statut : <b>{event.status_badge}</b>\n\n"
            f"🏢 <b>{event.brand}</b> (à {event.distance_km} km)\n"
            f"📍 {event.address}, {event.postal_code} {event.city}\n\n"
            f"✨ <b>Carburants de nouveau disponibles :</b>\n"
        )
        for f in event.fuels_restocked:
            price_str = f"<b>{f.price:.3f} €/L</b>" if f.price else "<i>Prix non communiqué</i>"
            time_str = f"<i>({f.relative_time})</i>" if f.relative_time else ""
            text += f"• <b>{f.fuel}</b> : {price_str} {time_str}\n"

        if event.alternatives:
            text += f"\n🔄 <i>Alternatives en stock : {', '.join(event.alternatives)}</i>\n"

        text += f"\n📦 <i>Tous les carburants en stock : {', '.join(event.all_available)}</i>\n\n"
        text += f"🗺️ <a href=\"{event.google_maps_url}\">Itinéraire Google Maps</a> | <a href=\"{event.waze_url}\">Waze</a>"

        return self._send_message(text)

    def send_test_message(self) -> bool:
        text = (
            "✅ <b>SP-Bot : Test Telegram réussi !</b>\n"
            "Modèle de surveillance type Gasoil Now / Essence&CO actif."
        )
        return self._send_message(text)
