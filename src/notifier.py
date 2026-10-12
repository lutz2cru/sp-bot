import json
import time
import urllib.error
import urllib.request
from typing import Dict, List, Tuple

from src.tracker import RestockEvent, normalize_fuel
from src.fetcher import Station
from src.fetcher import opening_label
from src.config import NtfyConfig
from src.timeutil import format_relative_time

POST_ATTEMPTS = 3

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
        """Publie sur Ntfy avec reprises. True uniquement si le serveur a accusé réception."""
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SP-Bot/2.0"
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"

        for attempt in range(POST_ATTEMPTS):
            wait = 3 * (attempt + 1)
            try:
                req = urllib.request.Request(self.server, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in (200, 201):
                        return True
                    print(f"[!] Erreur Ntfy : HTTP {resp.status}")
            except urllib.error.HTTPError as e:
                print(f"[!] Erreur Ntfy : HTTP {e.code}")
                if e.code == 429:  # quota du serveur public : on respecte le délai demandé
                    try:
                        wait = min(int(e.headers.get("Retry-After", wait)), 20)
                    except (TypeError, ValueError):
                        pass
                elif e.code < 500:
                    return False  # requête refusée : réessayer à l'identique ne changera rien
            except Exception as e:
                print(f"[!] Erreur Ntfy : {e}")
            if attempt < POST_ATTEMPTS - 1:
                time.sleep(wait)
        return False

    def send_stock_event(self, event: RestockEvent) -> bool:
        """Envoie une notification push instantanée pour un réapprovisionnement (RESTOCK) ou une rupture (SHORTAGE)."""
        if getattr(event, "event_type", "RESTOCK") == "SHORTAGE":
            fuels_str = " / ".join(event.fuels_affected)
            title = f"🔴 RUPTURE {fuels_str} : {event.brand} ({event.city})"
            lines = [
                f"⛽ {event.brand} - {event.address}, {event.city} ({event.distance_km} km)",
                f"❌ {fuels_str} n'est plus disponible (rupture de stock)."
            ]
            if event.alternatives:
                lines.append(f"🔄 Alternatives encore en stock : {', '.join(event.alternatives)}")
            elif event.all_available:
                lines.append(f"🔄 Autres carburants en stock : {', '.join(event.all_available)}")
            else:
                lines.append("⚠️ Station désormais en rupture totale !")
            if event.verification:
                lines.append(f"✅ Vérifié : {event.verification}")

            payload = {
                "topic": self.topic,
                "title": title,
                "message": "\n".join(lines).strip(),
                "priority": 3,
                "tags": ["warning", "fuelpump", "no_entry"],
                "actions": [
                    {"action": "view", "label": "Google Maps", "url": event.google_maps_url}
                ]
            }
            return self._post(payload)

        # Cas RESTOCK (de nouveau disponible)
        fuels_parts = []
        for f in event.fuels_restocked:
            p_str = f" ({f.price:.3f} €/L)" if f.price else ""
            fuels_parts.append(f"{f.fuel}{p_str}")
        fuels_summary = ", ".join(fuels_parts)

        title = f"🟢 DISPO : {fuels_summary} à {event.city}"
        lines = [
            f"⛽ {event.brand} - {event.address}, {event.city} ({event.distance_km} km)",
        ]
        for f in event.fuels_restocked:
            p_str = f"{f.price:.3f} €/L" if f.price else "Prix dispo"
            # Recalculé à l'envoi : l'alerte peut avoir attendu dans la file
            rel = format_relative_time(f.maj)
            rel_str = f"(déclaré à {f.maj[11:16]}, {rel})" if rel else ""
            lines.append(f"✨ {f.fuel} : {p_str} {rel_str}".strip())

        if event.verification:
            lines.append(f"✅ Vérifié : {event.verification}")
        opening = opening_label(event.automate_24_24, event.hours)
        if opening:
            lines.append(f"🕐 {opening}")
        if event.alternatives:
            lines.append(f"🔄 Alternatives : {', '.join(event.alternatives)}")

        payload = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(lines).strip(),
            "priority": self.config.priority,
            "tags": ["fuelpump", "white_check_mark"],
            "actions": [
                {"action": "view", "label": "Google Maps", "url": event.google_maps_url},
                {"action": "view", "label": "Waze", "url": event.waze_url}
            ]
        }
        return self._post(payload)

    send_restock_event = send_stock_event

    def send_stock_list(self, stations: List[Station], target_fuels: List[str]) -> bool:
        """Envoie la liste en direct de toutes les stations Total ayant les carburants ciblés en stock."""
        norm_targets = [normalize_fuel(tf) for tf in target_fuels]
        available_stations: List[Tuple[Station, List[str]]] = []

        for s in stations:
            matched_fuels = [f for f in s.disponibles if normalize_fuel(f) in norm_targets]
            if matched_fuels:
                available_stations.append((s, matched_fuels))

        if available_stations:
            cities = list(dict.fromkeys(s.city for s, _ in available_stations))
            cities_str = ", ".join(cities)
            title = f"⛽ Total : {len(available_stations)} station(s) en stock ({cities_str})"
            lines = []

            for s, fuels in available_stations:
                fuel_strs = []
                for f in fuels:
                    p = s.prices.get(f, {})
                    val_str = f"{p.get('valeur'):.3f} €" if p.get('valeur') else "Prix dispo"
                    fuel_strs.append(f"{f} ({val_str})")

                lines.append(f"• {s.city} : {' / '.join(fuel_strs)} | {s.brand} ({s.distance_km} km)")
                lines.append(f"  📍 {s.address}")

            rupture_count = len(stations) - len(available_stations)
            if rupture_count > 0:
                lines.append(f"🔴 {rupture_count} autre(s) station(s) en rupture.")

            actions = []
            first_station = available_stations[0][0]
            actions.append({"action": "view", "label": f"Maps {first_station.city}", "url": first_station.google_maps_url})
            actions.append({"action": "view", "label": f"Waze {first_station.city}", "url": first_station.waze_url})
            if len(available_stations) > 1:
                second_station = available_stations[1][0]
                actions.append({"action": "view", "label": f"Maps {second_station.city}", "url": second_station.google_maps_url})

            tags = ["fuelpump", "white_check_mark"]
        else:
            fuel_label = " / ".join(target_fuels)
            title = f"⚠️ Pénurie : 0 station Total avec {fuel_label}"
            lines = [
                f"🔴 Aucune des {len(stations)} stations surveillées n'a de {fuel_label} en stock."
            ]
            actions = []
            tags = ["fuelpump", "warning"]

        payload = {
            "topic": self.topic,
            "title": title,
            "message": "\n".join(lines).strip(),
            "priority": self.config.priority,
            "tags": tags,
        }
        if actions:
            payload["actions"] = actions[:3]
        return self._post(payload)

    def send_system(self, title: str, message: str, tags: List[str]) -> bool:
        """Message de service (panne ou rétablissement de la source de données)."""
        return self._post({"topic": self.topic, "title": title, "message": message, "priority": 3, "tags": tags})

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

    def send_stock_event(self, event: RestockEvent) -> bool:
        return self.notifier.send_stock_event(event)

    def send_system(self, title: str, message: str, tags: List[str]) -> bool:
        return self.notifier.send_system(title, message, tags)

    def broadcast_stock_event(self, event: RestockEvent) -> int:
        return 1 if self.notifier.send_stock_event(event) else 0

    broadcast_restock = broadcast_stock_event

    def broadcast_stock_list(self, stations: List[Station], target_fuels: List[str]) -> bool:
        return self.notifier.send_stock_list(stations, target_fuels)

    def send_test_all(self) -> Dict[str, bool]:
        return {self.notifier.name: self.notifier.send_test_message()}
