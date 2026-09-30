import os
import sys

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
from src.fetcher import Station
from src.tracker import FuelTracker

def test_simulation():
    print("[*] Test de simulation de réapprovisionnement (Modèle Gasoil Now / Essence&CO)...")
    tracker = FuelTracker(data_dir="data_test")
    config = Config()

    # Étape 1 : Station en rupture de Gazole
    station_initial = Station(
        id=90000015,
        brand="Total Access",
        address="56, AVENUE DU GENERAL LECLERC",
        city="Belfort",
        postal_code="90000",
        latitude=47.636,
        longitude=6.838,
        distance_km=2.0,
        zone_name="Belfort",
        status="RUPTURE_PARTIELLE",
        disponibles=["SP98"],
        rupture_temporaire=["Gazole", "SP95", "E10"],
        rupture_definitive=["E85", "GPLc"],
        prices={"SP98": {"valeur": 2.289, "maj": "2026-09-29 10:00:00", "relative_time": "il y a 1h"}},
        google_maps_url="https://maps.google.com/?q=47.636,6.838",
        waze_url="https://waze.com/ul?ll=47.636,6.838"
    )

    events_1 = tracker.process_stations([station_initial], config)
    print(f"Étape 1 (Initialisation) : {len(events_1)} événement (attendu: 0 car notify_on_startup=False)")
    assert len(events_1) == 0, "Étape 1 devrait avoir 0 événement."

    # Étape 2 : Le camion de livraison arrive ! Gazole et E10 de nouveau disponibles !
    station_restocked = Station(
        id=90000015,
        brand="Total Access",
        address="56, AVENUE DU GENERAL LECLERC",
        city="Belfort",
        postal_code="90000",
        latitude=47.636,
        longitude=6.838,
        distance_km=2.0,
        zone_name="Belfort",
        status="DISPONIBLE",
        disponibles=["Gazole", "E10", "SP98"],
        rupture_temporaire=[],
        rupture_definitive=["E85", "GPLc"],
        prices={
            "Gazole": {"valeur": 1.789, "maj": "2026-09-29 11:30:00", "relative_time": "à l'instant"},
            "E10": {"valeur": 1.829, "maj": "2026-09-29 11:30:00", "relative_time": "à l'instant"},
            "SP98": {"valeur": 2.289, "maj": "2026-09-29 10:00:00", "relative_time": "il y a 1h"}
        },
        google_maps_url="https://maps.google.com/?q=47.636,6.838",
        waze_url="https://waze.com/ul?ll=47.636,6.838"
    )

    events_2 = tracker.process_stations([station_restocked], config)
    print(f"Étape 2 (Après livraison) : {len(events_2)} événement(s) détecté(s) !")
    assert len(events_2) == 1, "Étape 2 devrait avoir 1 événement."

    ev = events_2[0]
    print(f"Station : {ev.brand} ({ev.city}) - Distance : {ev.distance_km} km")
    print(f"Statut badge : {ev.status_badge}")
    restocked_names = [f.fuel for f in ev.fuels_restocked]
    assert "E10" in restocked_names, "E10 doit être détecté"
    assert "Gazole" not in restocked_names, "Gazole ne doit PAS être notifié car seuls E10 et SP95 sont demandés"
    assert "SP98" not in restocked_names, "SP98 ne doit pas être redéclenché"

    # Étape 3 : Rupture de stock de E10 !
    station_shortage = Station(
        id=90000015,
        brand="Total Access",
        address="56, AVENUE DU GENERAL LECLERC",
        city="Belfort",
        postal_code="90000",
        latitude=47.636,
        longitude=6.838,
        distance_km=2.0,
        zone_name="Belfort",
        status="RUPTURE_PARTIELLE",
        disponibles=["Gazole", "SP98"],
        rupture_temporaire=["E10"],
        rupture_definitive=["E85", "GPLc"],
        prices={
            "Gazole": {"valeur": 1.789, "maj": "2026-09-29 11:30:00", "relative_time": "il y a 2h"},
            "SP98": {"valeur": 2.289, "maj": "2026-09-29 10:00:00", "relative_time": "il y a 3h"}
        },
        google_maps_url="https://maps.google.com/?q=47.636,6.838",
        waze_url="https://waze.com/ul?ll=47.636,6.838"
    )

    events_3 = tracker.process_stations([station_shortage], config)
    print(f"Étape 3 (Rupture de stock E10) : {len(events_3)} événement(s) détecté(s) !")
    assert len(events_3) == 1, "Étape 3 devrait détecter 1 événement de rupture."
    ev_shortage = events_3[0]
    assert ev_shortage.event_type == "SHORTAGE", "L'événement doit être de type SHORTAGE"
    assert "E10" in ev_shortage.fuels_affected, "E10 doit être marqué en rupture"
    print(f"Statut badge rupture : {ev_shortage.status_badge} - Carburant épuisé : {ev_shortage.fuels_affected}")

    # Étape 4 : Scan 5 minutes plus tard sans aucun changement -> 0 événement (zéro spam)
    events_4 = tracker.process_stations([station_shortage], config)
    print(f"Étape 4 (5 min plus tard, aucun changement) : {len(events_4)} événement (attendu: 0)")
    assert len(events_4) == 0, "Étape 4 ne doit générer aucun événement si rien n'a changé."

    # Étape 5 : Réapprovisionnement puis nœud API obsolète (test anti-flapping / stale cache)
    tracker.process_stations([station_restocked], config)  # re-dispo à 11:30
    stale_station = Station(
        id=90000015,
        brand="Total Access",
        address="56, AVENUE DU GENERAL LECLERC",
        city="Belfort",
        postal_code="90000",
        latitude=47.636,
        longitude=6.838,
        distance_km=2.0,
        zone_name="Belfort",
        status="RUPTURE_PARTIELLE",
        disponibles=["SP98"],
        rupture_temporaire=["Gazole", "SP95", "E10"],
        rupture_definitive=["E85", "GPLc"],
        prices={"SP98": {"valeur": 2.289, "maj": "2026-09-29 10:00:00", "relative_time": "il y a 1h"}},
        google_maps_url="https://maps.google.com/?q=47.636,6.838",
        waze_url="https://waze.com/ul?ll=47.636,6.838"
    )
    events_stale = tracker.process_stations([stale_station], config)
    print(f"Étape 5 (Nœud API obsolète renvoyant 10:00 au lieu de 11:30) : {len(events_stale)} événement (attendu: 0)")
    assert len(events_stale) == 0, "L'horodatage obsolète doit être rejeté sans déclencher de fausse rupture (anti-flapping)."

    # Étape 6 : Cas Menoncourt (station restockée à 11:30, puis nœud API obsolète renvoyant rupture totale SANS prix)
    stale_total_rupture_station = Station(
        id=90000015,
        brand="Total Access",
        address="56, AVENUE DU GENERAL LECLERC",
        city="Belfort",
        postal_code="90000",
        latitude=47.636,
        longitude=6.838,
        distance_km=2.0,
        zone_name="Belfort",
        status="RUPTURE_TOTALE",
        disponibles=[],
        rupture_temporaire=["Gazole", "SP95", "E10", "SP98"],
        rupture_definitive=[],
        prices={},
        google_maps_url="https://maps.google.com/?q=47.636,6.838",
        waze_url="https://waze.com/ul?ll=47.636,6.838",
        ruptures_detail={
            "E10": {"debut": "2026-09-29 08:00:00", "type": "temporaire"},
            "SP98": {"debut": "2026-09-29 08:00:00", "type": "temporaire"}
        }
    )
    events_stale_total = tracker.process_stations([stale_total_rupture_station], config)
    print(f"Étape 6 (Cas Menoncourt : rupture totale sur nœud sans prix avec rupture antérieure) : {len(events_stale_total)} événement (attendu: 0)")
    assert len(events_stale_total) == 0, "Le snapshot de rupture totale avec horodatage antérieur doit être rejeté sans déclencher de fausse rupture."

    # Nettoyage dossier test
    import shutil
    shutil.rmtree("data_test", ignore_errors=True)
    print("\n[+] TOUS LES TESTS DE SIMULATION (RÉAPPROVISIONNEMENT + RUPTURE + SILENCE + ANTI-FLAPPING COMPLET) ONT RÉUSSI AVEC SUCCÈS ! 🎉")

if __name__ == "__main__":
    test_simulation()
