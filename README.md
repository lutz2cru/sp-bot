# ⛽ SP-Bot : Alertes Réapprovisionnement Stations Total
### *Fonctionne 24h/24 sans laisser votre PC allumé (Modèle Gasoil Now & Essence&CO)*

Un bot intelligent en Python qui surveille en continu les stations **Total / TotalEnergies / Total Access** de votre secteur et vous alerte dès qu'un carburant est réapprovisionné et disponible à la pompe !

---

## ☁️ Faire tourner le bot 24h/24 sans laisser son PC allumé

Vous n'avez pas besoin de laisser votre ordinateur allumé. Le projet est configuré pour tourner **100% gratuitement dans le Cloud via GitHub Actions** :

### Mise en place en 3 minutes (Zéro frais, zéro serveur) :

1. **Créez un dépôt GitHub privé** (sur [github.com](https://github.com/new)).
2. **Poussez ce dossier de code** sur votre dépôt :
   ```powershell
   git init
   git add .
   git commit -m "Initial commit SP-Bot"
   git remote add origin https://github.com/VOTRE_PSEUDO/sp-bot.git
   git branch -M main
   git push -u origin main
   ```
3. **Ajoutez vos informations secrètes** dans GitHub :
   - Allez sur votre dépôt GitHub : **Settings** > **Secrets and variables** > **Actions** > **New repository secret**.
   - Ajoutez les variables suivantes selon vos préférences :
     - `EMAIL_USER` : votre adresse e-mail (ex: `votrecompte@gmail.com`)
     - `EMAIL_PASS` : votre mot de passe d'application (voir ci-dessous)
     - `EMAIL_TO` : l'adresse de réception (ex: `votrecompte@gmail.com`)
     - `NTFY_TOPIC` *(optionnel)* : le nom de votre canal de notification push

> **C'est tout !** Le workflow [`.github/workflows/fuel_monitor.yml`](file:///.github/workflows/fuel_monitor.yml) va s'exécuter automatiquement **toutes les 10 minutes, 24h/24 et 7j/7**. Dès qu'un camion livre du carburant, vous recevrez l'alerte sur votre téléphone sans que votre PC n'ait jamais besoin d'être allumé.

---

## 📬 Comparatif : E-mail vs Notification Push (Qu'est-ce qui est le plus efficient ?)

Le bot supporte **les deux méthodes**. Voici pourquoi l'une ou l'autre peut mieux vous convenir :

| Critère | ✉️ Par E-mail | 📲 Push Mobile (Ntfy) |
| :--- | :--- | :--- |
| **Rapidité de réception** | ⚠️ Dépend de la fréquence de synchro du smartphone (souvent toutes les 15-30 min) | ⚡ **Instantané à la seconde près** (vrai push natif) |
| **Visibilité / Alerte** | ⚠️ Peut se perdre au milieu des newsletters, spams ou factures | 🚨 **Bannière prioritaire + Sonnerie sur écran verrouillé** |
| **Facilité de configuration** | Nécessite de générer un mot de passe d'application SMTP | 🟢 **Zéro compte, zéro mot de passe, zéro serveur** |
| **Guidage GPS direct** | Boutons cliquables dans l'e-mail | Bouton Waze / Maps directement sous la notification |

👉 **Recommandation :** 
- Si vous préférez **centraliser vos alertes par e-mail**, activez le canal SMTP.
- Si vous voulez être le **premier arrivé à la pompe avant que la file d'attente ne se forme**, le push **Ntfy** est redoutablement plus efficient. Vous pouvez également **activer les deux en même temps** !

---

## ✉️ Configuration de l'E-mail (SMTP)

### Avec une adresse Gmail :
1. Activez la validation en 2 étapes sur votre compte Google si ce n'est pas déjà fait.
2. Rendez-vous sur la page officielle des mots de passe d'application : [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Créez un mot de passe nommé **"SP-Bot"** (Google vous donne un code de 16 lettres).
4. Renseignez-le dans [`config.json`](file:///c:/Users/matth/OneDrive%20-%20Universit%C3%A9%20De%20Technologie%20De%20Belfort-Montbeliard/Documents/CODE/sp-bot/config.json) :
   ```json
   "email": {
     "enabled": true,
     "smtp_host": "smtp.gmail.com",
     "smtp_port": 587,
     "use_tls": true,
     "username": "monadresse@gmail.com",
     "password": "mot_de_passe_16_lettres",
     "from_addr": "monadresse@gmail.com",
     "to_addrs": ["monadresse@gmail.com"]
   }
   ```
5. Testez immédiatement l'envoi :
   ```powershell
   python main.py test-notify
   ```

*(Fonctionne également avec Outlook / Hotmail : `smtp-mail.outlook.com` port `587`, ou Yahoo : `smtp.mail.yahoo.com` port `465`).*

---

## 📲 Configuration de Ntfy (La solution ultra-efficiente)

1. Installez l'application gratuite **ntfy** :
   - [ntfy pour Android (Google Play)](https://play.google.com/store/apps/details?id=io.heckel.ntfy) ou [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/)
   - [ntfy pour iPhone (App Store)](https://apps.apple.com/app/ntfy/id1625396347)
2. Appuyez sur **`+`** et choisissez un sujet unique (ex: `total-alerte-belfort-789`).
3. Mettez ce nom dans [`config.json`](file:///c:/Users/matth/OneDrive%20-%20Universit%C3%A9%20De%20Technologie%20De%20Belfort-Montbeliard/Documents/CODE/sp-bot/config.json) :
   ```json
   "ntfy": {
     "enabled": true,
     "topic": "total-alerte-belfort-789"
   }
   ```

---

## 🛠️ Commandes en local

```powershell
# Afficher le tableau de bord en direct (classement par distance, baromètre pénurie)
python main.py list

# Tester vos notifications (mail ou push)
python main.py test-notify

# Vérification ponctuelle
python main.py check

# Surveillance continue sur votre PC (si vous préférez le laisser tourner localement)
python main.py run
```

---

## 🐳 Déploiement Docker (Optionnel)

Si vous possédez un petit serveur VPS, un NAS ou un Raspberry Pi :
```bash
docker compose up -d --build
```
Le conteneur surveillera les stations 24h/24 en tâche de fond.
