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
- **Alertes vérifiées** : chaque changement est recoupé avec une seconde source officielle avant d'être envoyé (voir la section 6).
- **Aucune alerte perdue** : une notification reste en file d'attente tant que Ntfy n'a pas accusé réception.
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
> **Titre** : `🟢 DISPO : E10 (1.990 €/L) à Voujeaucourt`
> **Message** :
> ⛽ Total Access - Rue de la Cray, Voujeaucourt (4.1 km)
> ✨ E10 : 1.990 €/L (déclaré à 05:46, il y a 12 min)
> ✅ Vérifié : 2 sources officielles concordantes
> 🕐 Automate 24h/24
> 🔄 Alternatives : SP98 (1.990 €/L)
> **Actions 1-clic intégrées** :
> `[🗺️ Google Maps]` `[🚗 Waze]`

La ligne 🕐 indique si la station est réellement accessible maintenant (`Ouvert jusqu'à 18h00`, `Fermé · ouvre demain à 07h00`, `Automate 24h/24`).

### 🔴 Rupture de stock (Station épuisée)
> **Titre** : `🔴 RUPTURE E10 : Total Access (Belfort)`
> **Message** :
> ⛽ Total Access - 56 Avenue du Général Leclerc, Belfort (2.0 km)
> ❌ E10 n'est plus disponible (rupture de stock).
> 🔄 Alternatives encore en stock : SP98 (1.990 €/L)
> ✅ Vérifié : 2 sources officielles concordantes
> **Action intégrée** :
> `[🗺️ Google Maps]`

### ⚠️ Messages de service
Si la source de données officielle ne répond plus pendant plusieurs vérifications consécutives, le bot envoie **une** alerte `⚠️ SP-Bot : source de données injoignable`, puis `✅ SP-Bot : surveillance rétablie` au retour. Vous savez ainsi toujours si le silence signifie « rien n'a changé » ou « le bot est aveugle ».

---

## ☁️ 3. Fonctionnement 24h/24 dans le Cloud (GitHub Actions)

Vous n'avez **pas besoin de laisser votre ordinateur allumé**. Le robot tourne en tâche de fond sur les serveurs sécurisés de GitHub.

### Comment ça marche ?
1. Le fichier [`.github/workflows/fuel_monitor.yml`](.github/workflows/fuel_monitor.yml) est programmé pour tourner **toutes les 5 minutes** (`cron: '*/5 * * * *'`).
2. À chaque passage, il exécute `python main.py check`.
3. Si un changement de stock est repéré **et confirmé**, il envoie la notification push via Ntfy.
4. L'état des cuves et la file des alertes à envoyer sont archivés dans `data/state.json` par un commit automatique (uniquement lorsque quelque chose a changé).
5. Si la surveillance est dégradée (source injoignable de façon prolongée, alerte impossible à remettre), l'exécution est marquée **en échec** : GitHub vous prévient par e-mail.

> ℹ️ Le cron GitHub est souvent retardé de plusieurs minutes. Pour une cadence fiable, gardez un cron externe qui déclenche l'événement `repository_dispatch` de type `check-fuel`.

> 🔑 Optionnel : le serveur public ntfy.sh limite le nombre de messages par adresse IP, et celles de GitHub sont partagées. Si des envois sont refusés (HTTP 429), créez un jeton d'accès Ntfy et ajoutez-le comme secret `NTFY_TOKEN` du dépôt.

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

# 5. Simuler une vérification sans rien envoyer ni modifier l'état
python main.py check --dry-run

# 6. Lancer la suite de tests unitaires et de simulation
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
  "verification": {
    "cross_check": true,
    "confirm_minutes": 10,
    "stale_confirm_minutes": 30,
    "outage_alert_after_failures": 6
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
| `verification.cross_check` | Recoupe chaque changement avec le flux XML officiel avant d'alerter. | `true` |
| `verification.confirm_minutes` | Si le recoupement est impossible : durée pendant laquelle le changement doit persister avant l'alerte. | `10` |
| `verification.stale_confirm_minutes` | Idem pour un relevé plus ancien que l'état déjà validé (cache obsolète probable). | `30` |
| `verification.outage_alert_after_failures` | Nombre de vérifications en échec avant le message « source injoignable ». | `6` |
| `notify_on_startup` | Si `true`, envoie l'état de toutes les stations au tout premier lancement. | `false` |

---

## 🔬 6. Fiabilité : comment une alerte est vérifiée

### 📡 D'où proviennent les données ?
Deux sources officielles indépendantes, toutes deux alimentées par les déclarations obligatoires des stations :
1. **Source principale** : l'API [data.economie.gouv.fr](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/) (requêtes géographiques légères, interrogée à chaque passage).
2. **Source de recoupement** : le flux XML d'origine du ministère ([donnees.roulez-eco.fr](https://donnees.roulez-eco.fr/opendata/instantane_ruptures), ~1 Mo), téléchargé **uniquement** lorsqu'un changement doit être confirmé.

### ✅ Quand un carburant est-il considéré « en stock » ?
Il faut **à la fois** un prix valide et daté, et **aucune rupture en cours** déclarée pour ce carburant. Un prix accompagné d'une rupture active n'est pas compté comme disponible.

### 🛡️ Du relevé à la notification
| Situation | Comportement |
| :--- | :--- |
| Les deux sources concordent | Alerte immédiate, mention `2 sources officielles concordantes`. |
| Les deux sources se contredisent | Alerte **retenue** jusqu'à ce qu'elles soient d'accord. |
| Flux de recoupement injoignable | Alerte seulement si le changement persiste `confirm_minutes` sur au moins 2 relevés. |
| Relevé plus ancien que l'état validé (nœud de cache périmé) | Ignoré tant que la seconde source ne le confirme pas. |
| Erreur réseau / zone sans réponse | 3 tentatives, puis le dernier état connu est conservé : jamais de fausse rupture ni de faux réappro. |
| Ntfy injoignable ou saturé | 3 tentatives, puis l'alerte reste dans la file de `state.json` et repart au passage suivant. |
| « Dispo » jamais remis puis rupture | Les deux s'annulent : on ne vous envoie pas vers une pompe déjà vide. |

> ⚠️ **Limite à connaître** : le bot garantit que l'alerte reflète fidèlement ce que la station a **déclaré** aux autorités. Il ne peut pas voir les cuves : si un gérant tarde à déclarer une rupture, ou si la station est dévalisée dans les minutes qui suivent la livraison, aucune source de données ne permet de le savoir.

### ⚡ Optimisations & Sobriété
- **Requêtes ultra-légères** : Le bot filtre les champs demandés à l'API (`select=id,adresse,ville,cp,geom,prix,carburants_disponibles,...`). Chaque requête ne pèse que quelques Ko avec compression gzip.
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
1. **Cycle complet** : état de référence silencieux, réappro confirmé (seuls les carburants ciblés alertent), silence, rupture.
2. **Sans recoupement** : le changement doit persister ; un changement fugace n'est jamais notifié.
3. **Sources contradictoires** : aucune alerte tant qu'elles ne concordent pas.
4. **Cache obsolète** (cas Menoncourt) : pas de fausse rupture après une livraison validée.
5. **Pannes d'API** : zone manquante ou panne totale sans fausse alerte, message de service puis rétablissement.
6. **File d'envoi** : Ntfy en panne, redémarrage, remise différée, zéro doublon.
7. **Nouvelle station** et reprise de l'ancien format de `state.json`.
8. **Lecture du flux** : prix unique, conflit prix/rupture, horaires d'ouverture.

---

## 📄 Licence

Projet open-source distribué sous licence MIT. Libre d'utilisation et d'adaptation.
