from typing import List
from src.config import Config
from src.tracker import RestockEvent
from src.notifiers.base import BaseNotifier
from src.notifiers.ntfy import NtfyNotifier
from src.notifiers.telegram import TelegramNotifier
from src.notifiers.discord import DiscordNotifier
from src.notifiers.email_smtp import EmailNotifier

class NotificationManager:
    def __init__(self, config: Config):
        self.config = config
        self.notifiers: List[BaseNotifier] = []

        if config.ntfy.enabled and config.ntfy.topic:
            self.notifiers.append(NtfyNotifier(config.ntfy))
        if config.telegram.enabled and config.telegram.bot_token:
            self.notifiers.append(TelegramNotifier(config.telegram))
        if config.discord.enabled and config.discord.webhook_url:
            self.notifiers.append(DiscordNotifier(config.discord))
        if config.email.enabled and config.email.to_addrs:
            self.notifiers.append(EmailNotifier(config.email))

    @property
    def active_channels(self) -> List[str]:
        return [n.name for n in self.notifiers]

    def broadcast_restock(self, event: RestockEvent) -> int:
        """Envoie l'événement à tous les canaux configurés. Retourne le nombre d'envois réussis."""
        success_count = 0
        for n in self.notifiers:
            try:
                if n.send_restock_event(event):
                    success_count += 1
            except Exception as e:
                print(f"[!] Erreur notification ({n.name}): {e}")
        return success_count

    def send_test_all(self) -> dict:
        """Envoie un message de test à tous les canaux configurés."""
        results = {}
        for n in self.notifiers:
            try:
                ok = n.send_test_message()
                results[n.name] = ok
            except Exception as e:
                results[n.name] = False
                print(f"[!] Erreur test notification ({n.name}): {e}")
        return results
