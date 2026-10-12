import os
import sys
import json
import shutil
import tempfile
from datetime import datetime

# Ensure UTF-8 output on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.config import Config
from src.fetcher import FetchResult, build_station, opening_label, _as_list, _strip_at
from src.tracker import FuelTracker
from src.notifier import NtfyNotifier

SID = 90000015
DEFINITIVE = {"E85": ("2018-01-25 08:40:26", "definitive"), "GPLc": ("2024-05-02 11:35:26", "definitive")}

def make_station(prices=None, ruptures=None, sid=SID, automate=False):
    """prices : {carburant: (prix, maj)} ; ruptures : {carburant: (debut, type)}."""
    ruptures = {**DEFINITIVE, **(ruptures or {})}
    return build_station(
        sid, "Total Access", "56, AVENUE DU GENERAL LECLERC", "Belfort", "90000", 47.636, 6.838, 2.0, "Belfort",
        [{"nom": f, "valeur": str(v), "maj": maj} for f, (v, maj) in (prices or {}).items()],
        [{"nom": f, "debut": d, "fin": "", "type": t} for f, (d, t) in ruptures.items()],
        automate
    )

class FakeVerifier:
    """Simule le flux officiel de recoupement. stations=None : flux injoignable."""
    def __init__(self, stations=None):
        self.stations = stations
        self.calls = 0

    def lookup(self, station_ids):
        self.calls += 1
        if self.stations is None:
            return None
        return {s.id: s for s in self.stations if s.id in station_ids}

class FakeNotifier:
    def __init__(self, working=True):
        self.working = working
        self.sent = []

    def send_stock_event(self, event):
        if self.working:
            self.sent.append((event.event_type, tuple(event.fuels_affected)))
        return self.working

    def send_system(self, title, message, tags):
        if self.working:
            self.sent.append(("SYSTEM", title))
        return self.working

def make_config(**verification):
    config = Config()
    config.verification.confirm_minutes = 0
    config.verification.stale_confirm_minutes = 0
    for key, value in verification.items():
        setattr(config.verification, key, value)
    return config

def outbox(tracker):
    return tracker.load_state()["outbox"]

# États de référence de la station de test
SHORT = make_station({"SP98": (2.289, "2026-09-29 10:00:00")},
                     {"Gazole": ("2026-09-29 08:00:00", "temporaire"), "E10": ("2026-09-29 08:00:00", "temporaire")})
STOCKED = make_station({"Gazole": (1.789, "2026-09-29 11:30:00"), "E10": (1.829, "2026-09-29 11:30:00"),
                        "SP98": (2.289, "2026-09-29 10:00:00")})
E10_OUT = make_station({"Gazole": (1.789, "2026-09-29 11:30:00"), "SP98": (2.289, "2026-09-29 10:00:00")},
                       {"E10": ("2026-09-29 14:00:00", "temporaire")})

def test_cycle_complet(d):
    """Référence silencieuse, réappro confirmé par 2 sources, silence, rupture."""
    tracker, config = FuelTracker(data_dir=d), make_config()

    verifier = FakeVerifier([SHORT])
    assert tracker.process_stations([SHORT], config, verifier) == [], "le premier relevé ne doit rien notifier"
    assert verifier.calls == 0, "aucun téléchargement de recoupement sans changement à confirmer"

    events = tracker.process_stations([STOCKED], config, FakeVerifier([STOCKED]))
    assert len(events) == 1 and events[0].event_type == "RESTOCK"
    assert events[0].fuels_affected == ["E10"], "seuls les carburants ciblés déclenchent (pas le Gazole)"
    assert events[0].verification == "2 sources officielles concordantes"
    assert events[0].fuels_restocked[0].price == 1.829

    verifier = FakeVerifier([STOCKED])
    assert tracker.process_stations([STOCKED], config, verifier) == [], "aucun changement = aucun événement"
    assert verifier.calls == 0
    assert tracker.deliver_outbox(FakeNotifier()) == (1, 0)

    events = tracker.process_stations([E10_OUT], config, FakeVerifier([E10_OUT]))
    assert len(events) == 1 and events[0].event_type == "SHORTAGE" and events[0].fuels_affected == ["E10"]
    assert events[0].alternatives == ["SP98 (2.289 €/L)"]

def test_confirmation_sans_recoupement(d):
    """Flux de recoupement injoignable : il faut que le changement persiste sur plusieurs relevés."""
    tracker, config = FuelTracker(data_dir=d), make_config()
    down = FakeVerifier(None)
    tracker.process_stations([SHORT], config, down)
    assert tracker.process_stations([STOCKED], config, down) == [], "un seul relevé non recoupé ne suffit pas"
    events = tracker.process_stations([STOCKED], config, down)
    assert len(events) == 1 and events[0].verification == "confirmé sur 2 relevés consécutifs"

    # Avec un délai minimal, deux relevés rapprochés (même réponse en cache) ne suffisent pas
    tracker2, slow = FuelTracker(data_dir=os.path.join(d, "slow")), make_config(confirm_minutes=10)
    tracker2.process_stations([SHORT], slow, down)
    for _ in range(4):
        assert tracker2.process_stations([STOCKED], slow, down) == []

    # Un changement qui disparaît avant confirmation n'est jamais notifié
    tracker3 = FuelTracker(data_dir=os.path.join(d, "blip"))
    tracker3.process_stations([SHORT], config, down)
    assert tracker3.process_stations([STOCKED], config, down) == []
    assert tracker3.process_stations([SHORT], config, down) == []
    assert tracker3.process_stations([STOCKED], config, down) == [], "le compteur doit repartir de zéro"

def test_sources_contradictoires(d):
    """L'API annonce du stock mais le flux officiel dit rupture : on n'envoie personne à la pompe."""
    tracker, config = FuelTracker(data_dir=d), make_config()
    tracker.process_stations([SHORT], config, FakeVerifier([SHORT]))
    for _ in range(6):
        assert tracker.process_stations([STOCKED], config, FakeVerifier([SHORT])) == []
    # Dès que les deux sources concordent, l'alerte part
    assert len(tracker.process_stations([STOCKED], config, FakeVerifier([STOCKED]))) == 1

def test_cache_obsolete(d):
    """Cas Menoncourt : après une livraison validée, un nœud périmé ressert l'ancienne rupture."""
    tracker, config = FuelTracker(data_dir=d), make_config()
    tracker.process_stations([SHORT], config, FakeVerifier([SHORT]))
    tracker.process_stations([STOCKED], config, FakeVerifier([STOCKED]))

    stale_total = make_station({}, {"Gazole": ("2026-09-29 08:00:00", "temporaire"),
                                    "E10": ("2026-09-29 08:00:00", "temporaire"),
                                    "SP98": ("2026-09-29 08:00:00", "temporaire")})
    for stale in (SHORT, stale_total, SHORT):
        assert tracker.process_stations([stale], config, FakeVerifier([STOCKED])) == [], "fausse rupture sur cache obsolète"
    assert tracker.process_stations([STOCKED], config, FakeVerifier([STOCKED])) == [], "pas de faux réappro au retour"

def test_pannes_api(d):
    """Une erreur réseau ou une zone manquante ne doit produire ni fausse rupture ni faux réappro."""
    tracker, config = FuelTracker(data_dir=d), make_config(outage_alert_after_failures=3)
    other = make_station({"E10": (1.99, "2026-09-29 09:00:00")}, sid=70200006)
    verifier = FakeVerifier([STOCKED, other])
    tracker.process_stations([STOCKED, other], config, verifier)

    # Zone de Lure en échec : la station manque dans le relevé, puis revient
    partial = FetchResult(stations=[STOCKED], failed_zones=["Lure"], zones_total=2)
    assert tracker.process(partial, config, verifier) == []
    assert "70200006" in tracker.load_state()["stations"], "une station non relevée doit être conservée"
    assert tracker.process_stations([STOCKED, other], config, verifier) == [], "pas de faux réappro au retour de la zone"

    # Panne totale prolongée : une seule alerte de service, puis un message de rétablissement
    down = FetchResult(stations=[], failed_zones=["Belfort", "Lure"], zones_total=2)
    for _ in range(5):
        assert tracker.process(down, config, verifier) == []
    assert [e["title"] for e in outbox(tracker)] == ["⚠️ SP-Bot : source de données injoignable"]
    notifier = FakeNotifier()
    tracker.deliver_outbox(notifier)
    assert tracker.process_stations([STOCKED, other], config, verifier) == []
    tracker.deliver_outbox(notifier)
    assert [t for _, t in notifier.sent] == ["⚠️ SP-Bot : source de données injoignable", "✅ SP-Bot : surveillance rétablie"]

    # Premier relevé incomplet : la zone manquante est enregistrée en silence quand elle arrive
    fresh = FuelTracker(data_dir=os.path.join(d, "fresh"))
    assert fresh.process(partial, config, verifier) == []
    assert fresh.process_stations([STOCKED, other], config, verifier) == []

def test_file_envoi(d):
    """Ntfy en panne : l'alerte reste en file, part dès le rétablissement, et jamais deux fois."""
    tracker, config = FuelTracker(data_dir=d), make_config()
    tracker.process_stations([SHORT], config, FakeVerifier([SHORT]))
    tracker.process_stations([STOCKED], config, FakeVerifier([STOCKED]))

    broken, working = FakeNotifier(working=False), FakeNotifier()
    assert tracker.deliver_outbox(broken) == (0, 1)
    assert FuelTracker(data_dir=d).deliver_outbox(broken) == (0, 1), "la file doit survivre au redémarrage"
    assert outbox(tracker)[0]["attempts"] == 2
    assert FuelTracker(data_dir=d).deliver_outbox(working) == (1, 0)
    assert working.sent == [("RESTOCK", ("E10",))]
    assert tracker.deliver_outbox(working) == (0, 0) and len(working.sent) == 1, "aucun doublon"

    # Un « dispo » jamais remis suivi d'une rupture : les deux s'annulent, le téléphone ne reçoit rien
    tracker.process_stations([E10_OUT], config, FakeVerifier([E10_OUT]))
    tracker.deliver_outbox(working)
    restocked = make_station({"Gazole": (1.789, "2026-09-29 11:30:00"), "E10": (1.85, "2026-09-29 16:00:00"),
                              "SP98": (2.289, "2026-09-29 10:00:00")})
    out_again = make_station({"Gazole": (1.789, "2026-09-29 11:30:00"), "SP98": (2.289, "2026-09-29 10:00:00")},
                             {"E10": ("2026-09-29 17:00:00", "temporaire")})
    assert len(tracker.process_stations([restocked], config, FakeVerifier([restocked]))) == 1
    tracker.deliver_outbox(broken)
    assert tracker.process_stations([out_again], config, FakeVerifier([out_again])) == []
    assert outbox(tracker) == []

def test_nouvelle_station_et_migration(d):
    tracker, config = FuelTracker(data_dir=d), make_config()
    tracker.process_stations([SHORT], config, FakeVerifier([SHORT]))
    new = make_station({"E10": (1.99, "2026-09-29 09:00:00")}, sid=25420002, automate=True)
    events = tracker.process_stations([SHORT, new], config, FakeVerifier([SHORT, new]))
    assert len(events) == 1 and events[0].station_id == 25420002 and events[0].fuels_affected == ["E10"]

    # Ancien format de state.json : repris sans aucune alerte parasite
    legacy_dir = os.path.join(d, "legacy")
    os.makedirs(legacy_dir)
    with open(os.path.join(legacy_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"initialized": True, "last_check": "2026-09-29T12:00:00", "stations": {str(SID): {
            "brand": "Total Access", "city": "Belfort", "address": "x", "status": "DISPONIBLE", "distance_km": 2.0,
            "disponibles": ["Gazole", "E10", "SP98"], "rupture_temporaire": [], "rupture_definitive": ["E85", "GPLc"],
            "prices": {"E10": {"valeur": 1.829, "maj": "2026-09-29 11:30:00", "relative_time": "il y a 1h"}},
            "ruptures_detail": {}, "latest_update": "2026-09-29 11:30:00", "last_seen": "2026-09-29T12:00:00"}}}, f)
    legacy = FuelTracker(data_dir=legacy_dir)
    assert legacy.process_stations([STOCKED], config, FakeVerifier([STOCKED])) == []
    events = legacy.process_stations([E10_OUT], config, FakeVerifier([E10_OUT]))
    assert len(events) == 1 and events[0].event_type == "SHORTAGE"

def test_lecture_du_flux(d):
    # Un prix unique est sérialisé en objet et non en tableau par l'API
    single = _strip_at(_as_list('{"@nom": "GPLc", "@id": "4", "@maj": "2026-10-12 00:01:00", "@valeur": "0.999"}'))
    s = build_station(1, "Total", "", "", "", 0, 0, 0, "", single, [])
    assert s.disponibles == ["GPLc"] and s.prices["GPLc"]["valeur"] == 0.999
    assert _as_list(None) == [] and _as_list("pas du json") == []

    # Prix publié mais rupture en cours déclarée : le carburant n'est PAS considéré en stock
    conflict = make_station({"E10": (1.99, "2026-09-29 09:00:00")}, {"E10": ("2026-09-29 10:00:00", "temporaire")})
    assert "E10" not in conflict.disponibles and conflict.fuel_observation("E10")[0] is False
    # Prix sans date ou nul : ignoré
    assert make_station({"E10": (0, "2026-09-29 09:00:00"), "SP98": (1.9, "")}).disponibles == []
    # Rupture terminée (date de fin renseignée) : n'est plus une rupture
    ended = build_station(1, "Total", "", "", "", 0, 0, 0, "",
                          [{"nom": "E10", "valeur": "1.9", "maj": "2026-09-29 12:00:00"}],
                          [{"nom": "E10", "debut": "2026-09-29 08:00:00", "fin": "2026-09-29 11:00:00", "type": "temporaire"}])
    assert ended.disponibles == ["E10"]

    hours = {1: [["07.00", "18.00"]], 2: [["07.00", "18.00"]], 7: []}
    monday_noon, monday_night = datetime(2026, 10, 12, 12, 0), datetime(2026, 10, 12, 20, 0)
    assert opening_label(False, hours, monday_noon) == "Ouvert jusqu'à 18h00"
    assert opening_label(False, hours, monday_night) == "Fermé · ouvre demain à 07h00"
    assert opening_label(False, hours, datetime(2026, 10, 11, 12, 0)) == "Fermé · ouvre demain à 07h00"
    assert opening_label(True, hours, monday_night) == "Automate 24h/24"
    assert opening_label(False, {"1": [["07.00", "18.00"]]}, monday_noon) == "Ouvert jusqu'à 18h00", "clés JSON"
    assert opening_label(False, {}, monday_noon) == ""

def test_contenu_notification(d):
    tracker, config = FuelTracker(data_dir=d), make_config()
    tracker.process_stations([SHORT], config, FakeVerifier([SHORT]))
    tracker.process_stations([STOCKED], config, FakeVerifier([STOCKED]))

    ntfy, payloads = NtfyNotifier(config.ntfy), []
    ntfy._post = lambda payload: payloads.append(payload) or True
    assert tracker.deliver_outbox(ntfy) == (1, 0)
    message = payloads[0]["message"]
    assert payloads[0]["title"] == "🟢 DISPO : E10 (1.829 €/L) à Belfort"
    assert "✅ Vérifié : 2 sources officielles concordantes" in message
    assert "déclaré à 11:30" in message

if __name__ == "__main__":
    tests = [test_cycle_complet, test_confirmation_sans_recoupement, test_sources_contradictoires,
             test_cache_obsolete, test_pannes_api, test_file_envoi, test_nouvelle_station_et_migration,
             test_lecture_du_flux, test_contenu_notification]
    for test in tests:
        tmp = tempfile.mkdtemp(prefix="spbot_test_")
        try:
            test(tmp)
            print(f"[+] {test.__name__} : {test.__doc__.strip().splitlines()[0] if test.__doc__ else 'OK'}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n[+] LES {len(tests)} SCÉNARIOS DE SIMULATION ONT RÉUSSI ! 🎉")
