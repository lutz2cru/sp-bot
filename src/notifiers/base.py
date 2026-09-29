from abc import ABC, abstractmethod
from src.tracker import RestockEvent

class BaseNotifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Nom du canal de notification (ex: 'Ntfy', 'Telegram', 'Email')."""
        pass

    @abstractmethod
    def send_restock_event(self, event: RestockEvent) -> bool:
        """Envoie une notification pour un événement de réapprovisionnement."""
        pass

    @abstractmethod
    def send_test_message(self) -> bool:
        """Envoie un message de test pour valider la configuration."""
        pass
