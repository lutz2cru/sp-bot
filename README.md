# ⛽ SP-Bot : Surveillance Intelligente des Stations Total & Alertes Carburant en Direct

> **Robot autonome 24h/24** surveillant les stocks de carburant (**SP95** et **SP95-E10**) dans les stations **Total / TotalEnergies / Total Access** sur l'axe **Vesoul ↔ Lure (N19) ↔ Belfort ↔ Montbéliard**.  
> Notifications push instantanées sur smartphone via **Ntfy** : réapprovisionnements, ruptures de stock, guidage GPS en 1 clic et **zéro spam**.

---

## 🎯 En Bref

- **Secteur sous surveillance** : 13 stations Total réparties sur 4 zones stratégiques :
  - **Belfort** *(Intra-muros, Bavilliers, Menoncourt, Giromagny)*
  - **Montbéliard** *(Centre, Voujeaucourt, Valentigney, Aibre)*
  - **Lure & Axe N19**
  - **Vesoul** *(RN19 & Route de Paris)*
- **Carburants surveillés** : **SP95-E10** et **SP95** exclusivement (le bot ignore le Gazole, E85, GPLc et SP98 pour ne pas saturer vos notifications).
- **Zéro spam / 100 % utile** :
  - 🟢 **Alerte Réapprovisionnement** dès qu'une livraison de carburant arrive ou qu'une station repasse au vert (avec prix en direct et boutons GPS Google Maps / Waze).
  - 🔴 **Alerte Rupture** dès qu'une station tombe à sec sur ces carburants.
  - 🔇 **Silence total** entre les événements : aucun message inutile tant que la situation ne change pas.
- **Autonomie 24h/24 sans PC allumé** : Fonctionne gratuitement sur le cloud via GitHub Actions toutes les 5 minutes.
- **Ultra-léger & économe** : ~3,7 Ko par requête, moins de 0,2s de temps de réponse, aucune clé d'API requise.

---

## 📱 1. Réception des alertes sur smartphone (Ntfy)

Le bot utilise **Ntfy**, une solution de notification push libre, ultra-réactive, sans création de compte, sans publicité et sans pistage.

### Étape 1 : Télécharger l'application gratuite
- **Android** : [Télécharger sur Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) ou sur [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/)
- **iPhone / iOS** : [Télécharger sur l'App Store](https://apps.apple.com/app/ntfy/id1625396347)
- **Navigateur Web (PC / Mac)** : Directement accessible sur [ntfy.sh/sp-bot-alerte-total-belfort](https://ntfy.sh/sp-bot-alerte-total-belfort)

### Étape 2 : S'abonner au canal d'alerte
1. Ouvrez l'application **ntfy**.
2. Appuyez sur le bouton **`+`** *(S'abonner à un sujet)*.
3. Entrez le nom du sujet :  
   ```
   sp-bot-alerte-total-belfort
   ```
4. Validez. Vous êtes prêt à recevoir les alertes instantanées.

### Étape 3 : Tester la connexion
Depuis votre terminal, lancez :
```powershell
python main.py test-notify
```
Votre téléphone va immédiatement vibrer / sonner avec la notification de test.

---

## 🔔 2. À quoi ressemblent les alertes ?

### 🟢 Réapprovisionnement (Livraison détectée)
> **Titre** : `⛽ [Lure (Axe N19)] E10 DISPONIBLE : Total (Lure)`  
> **Message** :  
> 📍 16 Rue de Belfort, 70200 Lure (2.4 km)  
> Statut : 🟢 DISPONIBLE  
> ✨ Carburants de nouveau en stock :  
> • E10 : 1.990 €/L (il y a 5 min)  
> 🔄 Alternatives disponibles : SP98 (1.990 €/L)  
> **Actions 1-clic intégrées** :  
> `[🗺️ Google Maps]` `[🚗 Waze]`

### 🔴 Rupture de stock (Station épuisée)
> **Titre** : `⚠️ [Belfort] RUPTURE E10 : Total Access (Belfort)`  
> **Message** :  
> 📍 56 Avenue du Général Leclerc, 90000 Belfort (2.0 km)  
> Statut : 🔴 RUPTURE  
> 🔴 Carburant épuisé : E10 n'est plus disponible.  
> 🔄 Alternatives restantes : SP98 (1.990 €/L)  
> **Action intégrée** :  
> `[🗺️ Google Maps]`

---

## ☁️ 3. Fonctionnement 24h/24 dans le Cloud (GitHub Actions)

Vous n'avez **pas besoin de laisser votre ordinateur allumé**. Le robot tourne en tâche de fond sur les serveurs sécurisés de GitHub.

### Comment ça marche ?
1. Le fichier [`.github/workflows/fuel_monitor.yml`](.github/workflows/fuel_monitor.yml) est programmé pour tourner **toutes les 5 minutes** (`cron: '*/5 * * * *'`).
2. À chaque passage, il exécute `python main.py check`.
3. Si un changement de stock est repéré, il envoie la notification push via Ntfy.
4. L'état des cuves est automatiquement archivé dans `data/state.json` via un commit automatique pour comparer le stock lors du prochain passage.

### Avantages :
- **0 € de coût** (utilise les quotas gratuits GitHub Actions).
- **0 mot de passe ou secret à configurer** (Ntfy fonctionne sans token secret).
- Tout est déjà déployé et opérationnel sur votre dépôt.

---

## 💻 4. Commandes Utiles (Lancement Local)

Si vous souhaitez exécuter ou tester le bot sur votre propre machine :

```powershell
# 1. Afficher le tableau de bord complet en direct de toutes les stations surveillées
python main.py list

# 2. Lancer une vérification manuelle immédiate (alerte uniquement si changement)
python main.py check

# 3. Tester l'envoi d'une notification push vers votre smartphone
python main.py test-notify

# 4. Lancer la surveillance continue locale (boucle toutes les 3 minutes)
python main.py run

# 5. Lancer la suite de tests unitaires et de simulation
python tests/test_simulation.py
```

### Exemple de tableau de bord en direct (`python main.py list`) :
```text
===========================================================================
⛽ TABLEAU DE BORD DU SECTEUR (Modèle Gasoil Now / Essence&CO)
   Zones surveillées : Belfort (12 km) | Montbéliard (10 km) | Lure (Axe N19) (15 km) | Vesoul (12 km)
   Enseignes suivies : Total, Total Access, TotalEnergies
===========================================================================

📊 Baromètre du secteur (13 stations Total répertoriées) :
   🟢 Totalement approvisionnées : 1
   🟠 En rupture partielle       : 6
   🔴 En rupture totale          : 6
   ⚠️  Taux de stations impactées : 92.3%
---------------------------------------------------------------------------

[+] Classement par distance croissante :
⛽ [Belfort] TotalEnergies - 4 Faubourg de Brisach, 90000 Belfort
   📊 Statut : [🔴 RUPTURE TOTALE] | 📍 Distance : 0.3 km
   🟠 Rupture temporaire : Gazole, E10, SP98

⛽ [Lure (Axe N19)] Total - 16 Rue de Belfort, 70200 Lure
   📊 Statut : [🟠 RUPTURE PARTIELLE] | 📍 Distance : 2.4 km
   🟢 En stock : E10 (1.990 €/L) | SP98 (1.990 €/L)
   ...
```

---

## ⚙️ 5. Fichier de Configuration (`config.json`)

Le comportement du robot est entièrement personnalisable via le fichier [`config.json`](config.json) :

```json
{
  "location": {
    "mode": "zones",
    "zones": [
      {
        "name": "Belfort",
        "latitude": 47.6397,
        "longitude": 6.8638,
        "radius_km": 12
      },
      {
        "name": "Montbéliard",
        "latitude": 47.5100,
        "longitude": 6.7980,
        "radius_km": 10
      },
      {
        "name": "Lure (Axe N19)",
        "latitude": 47.6833,
        "longitude": 6.4917,
        "radius_km": 15
      },
      {
        "name": "Vesoul",
        "latitude": 47.6239,
        "longitude": 6.1555,
        "radius_km": 12
      }
    ]
  },
  "filters": {
    "brands": [
      "Total",
      "Total Access",
      "TotalEnergies"
    ],
    "fuels": [
      "E10",
      "SP95"
    ]
  },
  "ntfy": {
    "topic": "sp-bot-alerte-total-belfort",
    "server": "https://ntfy.sh",
    "priority": 4
  },
  "check_interval_seconds": 180,
  "notify_mode": "events_only",
  "notify_on_startup": false
}
```

### Explication des paramètres :
| Paramètre | Description | Valeur configurée |
| :--- | :--- | :--- |
| `location.zones` | Liste des secteurs géographiques avec coordonnées GPS et rayon de recherche en km. | Belfort, Montbéliard, Lure, Vesoul |
| `filters.brands` | Enseignes filtrées (détecte Total, Total Access, TotalEnergies). | `["Total", "Total Access", "TotalEnergies"]` |
| `filters.fuels` | Carburants ciblés pour les alertes. | `["E10", "SP95"]` |
| `ntfy.topic` | Nom du canal de notification Ntfy sur lequel s'abonner. | `sp-bot-alerte-total-belfort` |
| `notify_mode` | Mode d'envoi : `"events_only"` (uniquement si réapprovisionnement ou rupture) ou `"periodic_list"` (récapitulatif régulier). | `"events_only"` |
| `notify_on_startup` | Si `true`, envoie l'état de toutes les stations au tout premier lancement. | `false` |

---

## 🔬 6. Précision des données & Architecture Technique

### 📡 D'où proviennent les données ?
Les données proviennent directement du **flux officiel en temps réel du Ministère de l'Économie et des Finances** via la plateforme [data.economie.gouv.fr](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/).
- Mise à jour légalement obligatoire pour toutes les stations-service débitant plus de 500 m³ par an.
- Actualisation du flux officiel toutes les 10 minutes par le gouvernement.

### ⚡ Optimisations & Sobriété
- **Requêtes ultra-légères** : Le bot filtre les champs demandés à l'API (`select=id,adresse,ville,cp,geom,prix,carburants_disponibles,...`). Chaque requête consomme à peine **3,7 Ko** de bande passante avec compression gzip.
- **Référentiel embarqué** : Le fichier [`data/total_stations.json`](data/total_stations.json) contient la cartographie des 2 327 stations Total de France (55 Ko), évitant de télécharger les 2 Mo de référentiel national à chaque tour.
- **Calculs géodésiques rapides** : Calcul précis des distances par la formule de Haversine sans passer par des API payantes ou lentes.
- **Moteur inspiré de Gasoil Now & Essence&CO** : Distinction fine entre rupture temporaire, rupture définitive, disponibilité et détection des livraisons récentes via les horodatages de révision de prix.

---

## 🧪 7. Validation & Tests

Le projet dispose d'une suite de tests complète simulant toutes les transitions possibles de stock :
```powershell
python tests/test_simulation.py
```
**Scénarios validés :**
1. **Initialisation** : Enregistrement de l'état de référence sans déclenchement d'alerte intempestive.
2. **Réapprovisionnement** : Arrivée d'un camion de livraison avec E10 et Gazole ➡️ Seul le E10 déclenche l'alerte (le Gazole est ignoré).
3. **Rupture de stock** : Épuisement du E10 ➡️ Déclenchement immédiat de l'alerte rupture avec indication des carburants restants.
4. **Silence / Anti-spam** : Scan suivant sans changement ➡️ Zéro alerte envoyée.

---

## 📄 Licence

Projet open-source distribué sous licence MIT. Libre d'utilisation et d'adaptation.
