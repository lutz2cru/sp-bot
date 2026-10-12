import os
import json
from datetime import timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple

from src.fetcher import Station, FetchResult
from src.config import Config
from src.timeutil import paris_now, utc_now_iso, minutes_since_utc_iso, format_relative_time

STATE_VERSION = 2
# Une station absente du flux est conservée telle quelle pendant ce délai avant d'être oubliée
STATION_RETENTION_DAYS = 14

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
    verification: str = ""  # Comment le changement a été confirmé
    automate_24_24: bool = False
    hours: Dict[Any, List[List[str]]] = field(default_factory=dict)

# Alias pour rétrocompatibilité
RestockEvent = StockChangeEvent

def event_from_dict(data: Dict[str, Any]) -> StockChangeEvent:
    data = dict(data)
    data["fuels_restocked"] = [RestockedFuel(**f) for f in data.get("fuels_restocked", [])]
    return StockChangeEvent(**data)

def _migrate_station_v1(old: Dict[str, Any]) -> Dict[str, Any]:
    """Convertit une entrée de l'ancien state.json (listes disponibles/ruptures) vers l'état par carburant."""
    prices = old.get("prices") or {}
    ruptures = old.get("ruptures_detail") or {}
    fuels: Dict[str, Any] = {}
    for f in old.get("disponibles") or []:
        p = prices.get(f) or {}
        fuels[f] = {"available": True, "since": p.get("maj", ""), "price": p.get("valeur")}
    for f in (old.get("rupture_temporaire") or []) + (old.get("rupture_definitive") or []):
        if f not in fuels:
            fuels[f] = {"available": False, "since": (ruptures.get(f) or {}).get("debut", ""), "price": None}
    return {
        "brand": old.get("brand", ""),
        "city": old.get("city", ""),
        "address": old.get("address", ""),
        "zone": "",
        "distance_km": old.get("distance_km", 0.0),
        "fuels": fuels,
        "pending": {},
        "last_seen": str(old.get("last_seen", ""))[:10]
    }

class FuelTracker:
    """Machine à états par station et par carburant.

    - Un changement n'est validé (et notifié) qu'une fois confirmé : soit par le flux officiel de
      recoupement, soit parce qu'il persiste sur plusieurs relevés espacés.
    - Les alertes validées passent par une file d'envoi persistée dans state.json : elles y restent
      tant que Ntfy n'a pas accusé réception.
    """
    def __init__(self, data_dir: str = "data", dry_run: bool = False):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, data_dir) if not os.path.isabs(data_dir) else data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.state_file = os.path.join(self.data_dir, "state.json")
        self.dry_run = dry_run
        self._state: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ persistance

    def load_state(self) -> Dict[str, Any]:
        """Charge l'état précédent des stations (et migre l'ancien format si besoin)."""
        state: Dict[str, Any] = {}
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception as e:
                # Fichier corrompu : on repart d'un état de référence silencieux plutôt que d'alerter à tort
                print(f"[!] Erreur de lecture de state.json : {e}")
                state = {}

        stations = state.get("stations") or {}
        if state.get("version") != STATE_VERSION:
            stations = {sid: (st if "fuels" in st else _migrate_station_v1(st)) for sid, st in stations.items()}
        return {
            "version": STATE_VERSION,
            "initialized": bool(state.get("initialized", False)),
            "consecutive_failures": int(state.get("consecutive_failures", 0)),
            "outage_notified": bool(state.get("outage_notified", False)),
            "stations": stations,
            "outbox": list(state.get("outbox") or [])
        }

    def _current_state(self) -> Dict[str, Any]:
        # En simulation rien n'est écrit : l'état de travail ne vit qu'en mémoire
        return self._state if (self.dry_run and self._state) else self.load_state()

    def save_state(self, state: Dict[str, Any]) -> None:
        """Sauvegarde atomique ; le fichier n'est pas réécrit si rien n'a changé (pas de commit inutile)."""
        self._state = state
        if self.dry_run:
            return
        content = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    if f.read() == content:
                        return
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            os.replace(tmp, self.state_file)
        except Exception as e:
            print(f"[!] Erreur d'écriture de state.json : {e}")

    # ------------------------------------------------------------------ détection

    def process_stations(self, stations: List[Station], config: Config, verifier: Any = None) -> List[StockChangeEvent]:
        """Compatibilité : traite un relevé considéré comme complet."""
        return self.process(FetchResult(stations=list(stations), zones_total=1), config, verifier)

    def process(self, result: FetchResult, config: Config, verifier: Any = None) -> List[StockChangeEvent]:
        """
        Compare le relevé à l'état validé et retourne les changements CONFIRMÉS (également placés
        dans la file d'envoi) :
        1. Les réapprovisionnements (RESTOCK) : un carburant ciblé redevient disponible.
        2. Les ruptures (SHORTAGE) : un carburant ciblé tombe en rupture de stock.
        """
        state = self._current_state()
        ver = config.verification

        # Panne de la source : on ne touche à aucune station (jamais de fausse alerte sur une erreur réseau)
        if not result.ok:
            state["consecutive_failures"] += 1
            if state["consecutive_failures"] >= ver.outage_alert_after_failures and not state["outage_notified"]:
                state["outage_notified"] = True
                self._enqueue_system(state, "outage", "⚠️ SP-Bot : source de données injoignable",
                                     f"L'API officielle des carburants ne répond plus depuis {state['consecutive_failures']} "
                                     "vérifications. Les alertes sont suspendues jusqu'au rétablissement.",
                                     ["warning", "electric_plug"])
            self.save_state(state)
            return []

        if state["outage_notified"]:
            self._enqueue_system(state, "recovery", "✅ SP-Bot : surveillance rétablie",
                                 "La source de données répond de nouveau. Les alertes reprennent normalement.",
                                 ["white_check_mark"])
        state["consecutive_failures"] = 0
        state["outage_notified"] = False

        baseline = not state["initialized"] and not config.notify_on_startup
        target_fuels = [normalize_fuel(f) for f in config.filters.fuels]
        today = paris_now().strftime("%Y-%m-%d")
        now_iso = utc_now_iso()
        entries = state["stations"]
        candidates: List[Tuple[Station, str]] = []

        for s in result.stations:
            sid = str(s.id)
            entry = entries.get(sid) or {"fuels": {}, "pending": {}}
            entry.update({"brand": s.brand, "city": s.city, "address": s.address, "zone": s.zone_name,
                          "distance_km": s.distance_km, "last_seen": today})
            entries[sid] = entry
            fuels, pending = entry["fuels"], entry["pending"]

            for fuel in sorted(set(s.prices) | set(s.ruptures_detail) | set(s.disponibles) | set(fuels)):
                avail, ts, price = s.fuel_observation(fuel)
                is_target = normalize_fuel(fuel) in target_fuels
                conf = fuels.get(fuel)

                if conf is None:
                    if baseline or not is_target or not avail:
                        fuels[fuel] = {"available": avail, "since": ts, "price": price}
                        continue
                    # Carburant ciblé annoncé en stock sur une station encore inconnue : à confirmer comme les autres
                    conf = fuels[fuel] = {"available": False, "since": "", "price": None}

                if avail == conf["available"]:
                    pending.pop(fuel, None)
                    if ts >= (conf.get("since") or ""):
                        conf["since"], conf["price"] = ts, price
                    continue

                if not is_target:
                    fuels[fuel] = {"available": avail, "since": ts, "price": price}
                    continue

                p = pending.get(fuel)
                if p and p.get("available") == avail:
                    p["seen"] = int(p.get("seen", 1)) + 1
                    p["ts"] = ts
                else:
                    pending[fuel] = {"available": avail, "ts": ts, "seen": 1, "first_seen": now_iso}
                candidates.append((s, fuel))

        # Recoupement : le flux officiel n'est téléchargé que s'il y a quelque chose à confirmer
        cross: Optional[Dict[int, Station]] = None
        if candidates and verifier is not None and ver.cross_check:
            cross = verifier.lookup(sorted({s.id for s, _ in candidates}))

        confirmed: Dict[int, Dict[str, Any]] = {}
        for s, fuel in candidates:
            entry = entries[str(s.id)]
            conf, p = entry["fuels"][fuel], entry["pending"][fuel]
            avail, ts, price = s.fuel_observation(fuel)

            # Relevé plus ancien que l'état déjà validé : très probablement un nœud de cache obsolète
            stale = bool(ts and conf.get("since") and ts < conf["since"])
            agrees: Optional[bool] = None
            if cross is not None and s.id in cross:
                agrees = cross[s.id].fuel_observation(fuel)[0] == avail

            waited = minutes_since_utc_iso(p["first_seen"])
            label = ""
            if agrees is False:
                print(f"[~] {s.city} [{s.id}] {fuel} : les deux sources officielles se contredisent, alerte retenue.")
            elif agrees and (not stale or p["seen"] >= 2):
                label = "2 sources officielles concordantes"
            elif agrees is None and p["seen"] >= 2 and waited >= (ver.stale_confirm_minutes if stale else ver.confirm_minutes):
                label = f"confirmé sur {p['seen']} relevés consécutifs"
            if not label:
                if agrees is not False:
                    print(f"[~] {s.city} [{s.id}] {fuel} : changement en attente de confirmation (relevé n°{p['seen']}).")
                continue

            entry["fuels"][fuel] = {"available": avail, "since": ts, "price": price}
            del entry["pending"][fuel]
            bucket = confirmed.setdefault(s.id, {"station": s, "restock": [], "shortage": [], "labels": []})
            bucket["restock" if avail else "shortage"].append(fuel)
            if label not in bucket["labels"]:
                bucket["labels"].append(label)

        events: List[StockChangeEvent] = []
        for bucket in confirmed.values():
            s, verification = bucket["station"], " / ".join(bucket["labels"])
            if bucket["restock"]:
                events.append(self._build_event(s, "RESTOCK", bucket["restock"], verification))
            if bucket["shortage"]:
                events.append(self._build_event(s, "SHORTAGE", bucket["shortage"], verification))

        if result.complete:
            # L'état de référence n'est acquis qu'après un relevé complet de toutes les zones
            state["initialized"] = True
            limit = (paris_now() - timedelta(days=STATION_RETENTION_DAYS)).strftime("%Y-%m-%d")
            for sid in [k for k, v in entries.items() if (v.get("last_seen") or today) < limit]:
                del entries[sid]

        queued = [ev for ev in events if self._enqueue_event(state, ev)]
        self.save_state(state)
        return queued

    def _build_event(self, s: Station, event_type: str, fuels: List[str], verification: str) -> StockChangeEvent:
        alternatives: List[str] = []
        for fuel in fuels:
            for alt in FUEL_ALTERNATIVES.get(normalize_fuel(fuel), []):
                if alt.lower() != fuel.lower() and alt in s.disponibles and alt not in fuels:
                    p = s.prices.get(alt, {}).get("valeur")
                    alt_entry = f"{alt} ({p:.3f} €/L)" if p else alt
                    if alt_entry not in alternatives:
                        alternatives.append(alt_entry)

        restocked: List[RestockedFuel] = []
        if event_type == "RESTOCK":
            badge = "🟢 DISPONIBLE" if s.status == "DISPONIBLE" else "🟠 RUPTURE PARTIELLE"
            for fuel in fuels:
                info = s.prices.get(fuel, {})
                restocked.append(RestockedFuel(fuel=fuel, price=info.get("valeur"), maj=info.get("maj", ""),
                                               relative_time=format_relative_time(info.get("maj", ""))))
        else:
            badge = "🔴 RUPTURE TOTALE" if not s.disponibles else "🟠 RUPTURE PARTIELLE"

        return StockChangeEvent(
            station_id=s.id, brand=s.brand, address=s.address, city=s.city, postal_code=s.postal_code,
            latitude=s.latitude, longitude=s.longitude, distance_km=s.distance_km, zone_name=s.zone_name,
            status=s.status, status_badge=badge, fuels_restocked=restocked, all_available=list(s.disponibles),
            alternatives=alternatives, google_maps_url=s.google_maps_url, waze_url=s.waze_url,
            event_type=event_type, fuels_affected=list(fuels), verification=verification,
            automate_24_24=s.automate_24_24, hours=s.hours
        )

    # ------------------------------------------------------------------ file d'envoi

    def _enqueue_system(self, state: Dict[str, Any], kind: str, title: str, message: str, tags: List[str]) -> None:
        state["outbox"] = [e for e in state["outbox"] if e.get("kind") != "system"]
        state["outbox"].append({"id": f"system:{kind}:{utc_now_iso()}", "kind": "system", "created": utc_now_iso(),
                                "attempts": 0, "title": title, "message": message, "tags": tags})

    def _enqueue_event(self, state: Dict[str, Any], event: StockChangeEvent) -> bool:
        """Ajoute l'alerte à la file. Une alerte contraire encore non remise (ex. « dispo » jamais reçue
        suivie d'une « rupture ») s'annule avec la nouvelle : le téléphone n'a rien à corriger."""
        data = asdict(event)
        for queued in list(state["outbox"]):
            q = queued.get("event")
            if queued.get("kind") != "event" or not q:
                continue
            if q["station_id"] != event.station_id or q["event_type"] == event.event_type:
                continue
            common = set(q["fuels_affected"]) & set(data["fuels_affected"])
            if not common:
                continue
            for d in (q, data):
                d["fuels_affected"] = [f for f in d["fuels_affected"] if f not in common]
                d["fuels_restocked"] = [f for f in d["fuels_restocked"] if f["fuel"] not in common]
            if not q["fuels_affected"]:
                state["outbox"].remove(queued)
        if not data["fuels_affected"]:
            return False
        event.fuels_affected = data["fuels_affected"]
        event.fuels_restocked = [f for f in event.fuels_restocked if f.fuel in data["fuels_affected"]]
        now = utc_now_iso()
        state["outbox"].append({
            "id": f"{event.station_id}:{event.event_type}:{'+'.join(event.fuels_affected)}:{now}",
            "kind": "event", "created": now, "attempts": 0, "event": data
        })
        return True

    def pending_notifications(self) -> int:
        state = self._current_state()
        return len(state["outbox"])

    def deliver_outbox(self, notifier: Any) -> Tuple[int, int]:
        """Envoie tout ce qui attend dans la file. Une alerte n'en sort qu'après accusé de réception de Ntfy ;
        sinon elle est retentée à la vérification suivante. Retourne (envoyées, restantes)."""
        state = self._current_state()
        sent = 0
        for item in list(state["outbox"]):
            try:
                if item.get("kind") == "system":
                    ok = notifier.send_system(item["title"], item["message"], item.get("tags") or [])
                else:
                    ok = notifier.send_stock_event(event_from_dict(item["event"]))
            except Exception as e:
                print(f"[!] Erreur d'envoi de la notification {item.get('id')} : {e}")
                ok = False
            if ok:
                state["outbox"].remove(item)
                sent += 1
                self.save_state(state)  # immédiatement, pour ne jamais renvoyer une alerte déjà remise
            else:
                item["attempts"] = int(item.get("attempts", 0)) + 1
        self.save_state(state)
        return sent, len(state["outbox"])
