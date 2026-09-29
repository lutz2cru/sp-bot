# ⛽ SP-Bot : Alertes Réapprovisionnement Stations Total
### *Surveillance 24h/24 via le Cloud & Notifications Push instantanées (Ntfy)*

Un bot ultra-léger et efficient qui surveille en continu les stations **Total / TotalEnergies / Total Access** de votre secteur et vous alerte à la seconde près sur votre smartphone dès qu'un carburant est réapprovisionné !

---

## 📱 1. Comment recevoir les alertes sur votre téléphone (Ntfy)

Le bot utilise **Ntfy**, la solution la plus sobre et réactive du marché (sans compte, sans mot de passe, sans spam) :

1. Installez l'application gratuite **ntfy** :
   - [ntfy pour Android (Google Play)](https://play.google.com/store/apps/details?id=io.heckel.ntfy) ou [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/)
   - [ntfy pour iPhone (App Store)](https://apps.apple.com/app/ntfy/id1625396347)
2. Ouvrez l'application, appuyez sur **`+`** *(S'abonner à un sujet)* et entrez le nom du canal :  
   `sp-bot-alerte-total-belfort` *(ou celui configuré dans `config.json`)*.
3. Testez immédiatement la réception depuis votre terminal :
   ```powershell
   python main.py test-notify
   ```
   > Votre téléphone va immédiatement sonner avec la notification de test.

---

## ☁️ 2. Faire tourner le bot 24h/24 sans laisser son PC allumé

Vous n'avez pas besoin de laisser votre PC allumé. Le bot tourne gratuitement dans le cloud via **GitHub Actions** toutes les 10 minutes :

### Mise en place en 2 minutes (0 € et 0 mot de passe) :

1. Créez un dépôt GitHub **privé** sur votre compte (sur [github.com/new](https://github.com/new)).
2. Poussez ce dossier de code sur GitHub :
   ```powershell
   git remote add origin https://github.com/VOTRE_PSEUDO/sp-bot.git
   git branch -M main
   git push -u origin main
   ```

> **C'est tout !**  
> Puisque Ntfy ne nécessite aucun identifiant ni mot de passe, vous n'avez **aucun secret ni paramètre à renseigner**.  
> Le workflow [`.github/workflows/fuel_monitor.yml`](file:///.github/workflows/fuel_monitor.yml) va s'activer automatiquement et vérifier les cuves **toutes les 10 minutes, 24h/24**. Dès qu'une livraison a lieu, votre smartphone sonne instantanément.

---

## 🛠️ Commandes locales utiles

```powershell
# Afficher le tableau de bord en direct (distances GPS, baromètre pénurie, stock)
python main.py list

# Vérification ponctuelle manuelle
python main.py check

# Tester l'envoi de notification vers votre smartphone
python main.py test-notify

# Lancer la surveillance continue locale (toutes les 5 min)
python main.py run
```

---

## ⚙️ Configuration (`config.json`)

```json
{
  "location": {
    "mode": "gps",
    "latitude": 47.6397,
    "longitude": 6.8638,
    "radius_km": 20,
    "city": "Belfort",
    "department": "90"
  },
  "filters": {
    "brands": ["Total", "Total Access", "TotalEnergies"],
    "fuels": ["Gazole", "SP95", "E10", "SP98", "E85", "GPLc"]
  },
  "ntfy": {
    "topic": "sp-bot-alerte-total-belfort",
    "server": "https://ntfy.sh",
    "priority": 4
  },
  "check_interval_seconds": 300,
  "notify_on_startup": false
}
```
