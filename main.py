import os
import sys
import time
import argparse
from datetime import datetime

# Assure un affichage UTF-8 impeccable sur le terminal Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import load_config, Config
from src.fetcher import FuelFetcher, Station
from src.tracker import FuelTracker, RestockEvent
from src.notifier import NotificationManager

def format_price_and_time(prices: dict, fuel: str) -> str:
    p = prices.get(fuel)
    if p and p.get("valeur"):
        val_str = f"{p['valeur']:.3f} €/L"
        rel_str = f"({p.get('relative_time', '')})" if p.get("relative_time") else ""
        return f"{val_str} {rel_str}".strip()
    return "-"

def get_status_colored(status: str) -> str:
    if status == "DISPONIBLE":
        return "\033[1;32m[🟢 DISPONIBLE]\033[0m"
    elif status == "RUPTURE_PARTIELLE":
        return "\033[1;33m[🟠 RUPTURE PARTIELLE]\033[0m"
    else:
        return "\033[1;31m[🔴 RUPTURE TOTALE]\033[0m"

def display_station(s: Station, target_fuels: list):
    status_str = get_status_colored(s.status)
    print(f"\n⛽ [{s.id}] \033[1;36m{s.brand}\033[0m - {s.address}, {s.postal_code} {s.city}")
    print(f"   📊 Statut : {status_str} | 📍 Distance : \033[1;37m{s.distance_km} km\033[0m")
    print(f"   🗺️  {s.google_maps_url}")
    
    # Carburants disponibles avec prix et fraîcheur
    if s.disponibles:
        dispos_details = []
        for f in s.disponibles:
            p_info = format_price_and_time(s.prices, f)
            if p_info != "-":
                dispos_details.append(f"{f} \033[0;32m({p_info})\033[0m")
            else:
                dispos_details.append(f"{f}")
        print(f"   🟢 En stock : {' | '.join(dispos_details)}")
    else:
        print(f"   🔴 En stock : \033[1;31mAucun (Pénurie totale)\033[0m")
    
    # Ruptures temporaires
    if s.rupture_temporaire:
        print(f"   🟠 Rupture temporaire : \033[0;33m{', '.join(s.rupture_temporaire)}\033[0m")

def cmd_list(config: Config):
    print("=" * 75)
    print("⛽ TABLEAU DE BORD DU SECTEUR (Modèle Gasoil Now / Essence&CO)")
    print(f"   Centre : {config.location.city} ({config.location.latitude}, {config.location.longitude})")
    print(f"   Rayon de recherche : {config.location.radius_km} km | Tri : par proximité GPS")
    print(f"   Enseignes suivies : {', '.join(config.filters.brands)}")
    print("=" * 75)

    fetcher = FuelFetcher()
    stations = fetcher.fetch_stations(config)
    
    # Statistiques du secteur (Baromètre pénurie comme Essence&CO)
    total = len(stations)
    dispo_count = sum(1 for s in stations if s.status == "DISPONIBLE")
    partiel_count = sum(1 for s in stations if s.status == "RUPTURE_PARTIELLE")
    totale_count = sum(1 for s in stations if s.status == "RUPTURE_TOTALE")

    print(f"\n📊 Baromètre du secteur ({total} stations Total répertoriées) :")
    print(f"   🟢 Totalement approvisionnées : {dispo_count}")
    print(f"   🟠 En rupture partielle       : {partiel_count}")
    print(f"   🔴 En rupture totale          : {totale_count}")
    if total > 0:
        penurie_pct = round(((partiel_count + totale_count) / total) * 100, 1)
        print(f"   ⚠️  Taux de stations impactées : {penurie_pct}%")
    print("-" * 75)

    print(f"\n[+] Classement par distance croissante :")
    for s in stations:
        display_station(s, config.filters.fuels)
    print("\n" + "=" * 75)

def cmd_check(config: Config, send_notifications: bool = True):
    print(f"[*] [{datetime.now().strftime('%H:%M:%S')}] Analyse du secteur (modèle temps réel Gasoil Now)...")
    fetcher = FuelFetcher()
    tracker = FuelTracker()
    notifier = NotificationManager(config)

    stations = fetcher.fetch_stations(config)
    print(f"[*] {len(stations)} station(s) surveillée(s) dans un rayon de {config.location.radius_km} km.")

    events = tracker.process_stations(stations, config)

    if not events:
        print("[*] Aucun nouveau réapprovisionnement détecté.")
        return

    print(f"\n🚨 \033[1;32m{len(events)} RÉAPPROVISIONNEMENT(S) DÉTECTÉ(S) !\033[0m")
    for ev in events:
        print(f"\n✨ {ev.status_badge} : {ev.brand} ({ev.city} - {ev.distance_km} km)")
        print(f"   Adresse : {ev.address}")
        for rf in ev.fuels_restocked:
            p_str = f"{rf.price:.3f} €/L" if rf.price else "Prix non précisé"
            rel_str = f"({rf.relative_time})" if rf.relative_time else ""
            print(f"   -> Carburant disponible : \033[1;32m{rf.fuel}\033[0m ({p_str}) {rel_str}")
        if ev.alternatives:
            print(f"   -> Alternatives en stock : {', '.join(ev.alternatives)}")
        print(f"   Lien : {ev.google_maps_url}")

        if send_notifications:
            sent = notifier.broadcast_restock(ev)
            print(f"   📲 Alertes expédiées avec succès vers {sent} canal/canaux.")

def cmd_run(config: Config):
    notifier = NotificationManager(config)
    active = notifier.active_channels
    channels_str = ", ".join(active) if active else "Aucun (Activez Ntfy, Telegram ou Email dans config.json)"

    print("=" * 75)
    print("🚀 DÉMARRAGE DE LA SURVEILLANCE CONTINUE (Modèle Gasoil Now / Essence&CO)")
    print(f"   Secteur : {config.location.city} (Rayon: {config.location.radius_km} km)")
    print(f"   Fréquence de scan : toutes les {config.check_interval_seconds} secondes")
    print(f"   Canaux de notification actifs : {channels_str}")
    print("   Arrêt : CTRL+C à tout moment.")
    print("=" * 75)

    try:
        while True:
            cmd_check(config, send_notifications=True)
            print(f"\n[*] Prochaine vérification dans {config.check_interval_seconds}s... (CTRL+C pour quitter)")
            time.sleep(config.check_interval_seconds)
    except KeyboardInterrupt:
        print("\n\n[!] Surveillance interrompue par l'utilisateur. À bientôt !")

def cmd_test_notify(config: Config):
    print("=" * 75)
    print("🧪 TEST DES CANAUX DE NOTIFICATION")
    print("=" * 75)
    notifier = NotificationManager(config)
    if not notifier.notifiers:
        print("[!] Aucun canal de notification n'est activé dans config.json !")
        return

    print(f"[*] Envoi d'un message test vers : {', '.join(notifier.active_channels)}...")
    results = notifier.send_test_all()
    for name, success in results.items():
        if success:
            print(f"  [+] \033[1;32m{name} : Message envoyé avec succès !\033[0m")
        else:
            print(f"  [-] \033[1;31m{name} : Échec de l'envoi.\033[0m")
    print("=" * 75)

def main():
    parser = argparse.ArgumentParser(
        description="SP-Bot : Surveillance et alertes de réapprovisionnement des stations Total."
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="check",
        choices=["check", "run", "list", "test-notify"],
        help="Action à exécuter : 'check' (vérification), 'run' (boucle), 'list' (dashboard), 'test-notify' (test alertes)."
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config.json",
        help="Chemin vers le fichier de configuration JSON (défaut: config.json)."
    )

    args = parser.parse_args()
    config = load_config(args.config)

    if args.action == "list":
        cmd_list(config)
    elif args.action == "check":
        cmd_check(config, send_notifications=True)
    elif args.action == "run":
        cmd_run(config)
    elif args.action == "test-notify":
        cmd_test_notify(config)

if __name__ == "__main__":
    main()
