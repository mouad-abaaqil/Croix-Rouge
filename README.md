<div align="center">
  <img src="assets/croix_rouge_logo.png" alt="Logo Croix-Rouge" width="112">
  <h1>Red Collect</h1>
  <p><strong>Des collectes plus simples à organiser, du premier point au retour au dépôt.</strong></p>
  <p>Application open source de suivi des points de collecte et de préparation de tournées · Calais</p>
  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-red.svg" alt="Licence MIT"></a>
    <img src="https://img.shields.io/badge/interface-Fran%C3%A7ais%20%7C%20English-29313a" alt="Français et anglais">
    <img src="https://img.shields.io/badge/status-prototype%20open%20source-25806a" alt="Prototype open source">
  </p>
</div>

<p align="center">
  <img src="assets/redcollect-demo.gif" alt="Démonstration silencieuse : tableau de bord, carte, ajout par adresse, stocks, planification, missions, bénévoles et interface anglaise" width="100%">
</p>

<p align="center"><em>Défilement automatique de captures issues d’une base de démonstration, sans voix ni action sur des données réelles.</em></p>

**Français** · [English](#english)

---

## Français

Red Collect est une application web open source pour organiser une équipe de collecte. Elle rassemble sur une carte les points relais, leur niveau de remplissage et les missions à effectuer. Elle est conçue pour des coordinateurs et des bénévoles qui ne souhaitent pas manipuler des fichiers CSV ou saisir des coordonnées GPS.

Il n’y a pas d’instance publique hébergée : l’application se lance localement depuis ce dépôt. Les adresses, stocks et missions montrés dans les captures sont des données d’exemple.

### Démonstrations visuelles

La boucle silencieuse ci-dessus suit le parcours principal. Les captures individuelles permettent d’examiner les écrans en détail :

| Tableau de bord | Points et carte | Ajout par adresse |
|:--:|:--:|:--:|
| <img src="assets/screenshots/01-dashboard.png" alt="Tableau de bord avec urgences, stocks, missions et carte" width="320"> | <img src="assets/screenshots/02-points.png" alt="Liste filtrable et carte des points relais" width="320"> | <img src="assets/screenshots/07-address-search.png" alt="Formulaire d’ajout avec recherche d’adresse et repère ajustable" width="320"> |

| Mise à jour du stock | Planification et tournée | Suivi d’une mission |
|:--:|:--:|:--:|
| <img src="assets/screenshots/08-stock-update.png" alt="Dialogue de mise à jour d’un stock relais" width="320"> | <img src="assets/screenshots/04-route-preview.png" alt="Aperçu du trajet routier, des arrêts et des estimations" width="320"> | <img src="assets/screenshots/09-mission-progress.png" alt="Mission en cours avec carte, avancement, collecte et export" width="320"> |

| Vue bénévole | Partage par email | Équipe et dépôt |
|:--:|:--:|:--:|
| <img src="assets/screenshots/13-volunteer-mission.png" alt="Vue bénévole d’une mission qui lui est attribuée" width="320"> | <img src="assets/screenshots/10-email-preview.png" alt="Aperçu du récapitulatif email avant envoi" width="320"> | <img src="assets/screenshots/12-team-settings.png" alt="Paramètres du dépôt et gestion des comptes bénévoles" width="320"> |

[Voir aussi le tableau de bord en anglais](assets/screenshots/06-dashboard-en.png), [la liste des missions](assets/screenshots/11-missions-list.png) et [l’écran de préparation d’une tournée](assets/screenshots/03-planner.png).

### Fonctionnalités par rôle

| Fonction | Coordinateur | Bénévole |
|:--|:--:|:--:|
| Consulter le tableau de bord, la carte, les points et les missions | Oui | Oui |
| Mettre à jour le stock d’un point et enregistrer les kilos collectés | Oui | Oui |
| Ajouter ou modifier un point, ses capacités et son temps de collecte | Oui | — |
| Chercher une adresse et ajuster le repère directement sur la carte | Oui | — |
| Préparer et créer une tournée, choisir et réordonner les arrêts | Oui | — |
| Affecter une mission à un bénévole | Oui | — |
| Suivre une mission affectée ou non affectée, marquer un arrêt collecté/ignoré | Oui | Oui* |
| Gérer les comptes, le dépôt et les paramètres de démonstration | Oui | — |
| Exporter la mission en CSV et préparer/envoyer un récapitulatif par email | Oui | Export CSV |

\* Un bénévole peut mettre à jour une mission qui lui est affectée ou qui n’est pas affectée. Il ne peut pas modifier une mission attribuée à quelqu’un d’autre. Les liens de navigation ouvrent Google Maps sur l’arrêt sélectionné; le guidage GPS ne se fait pas dans Red Collect.

### Parcours courant

1. Le coordinateur vérifie le dépôt et la carte dans **Paramètres**.
2. Dans **Points de collecte**, il filtre les relais prioritaires, met à jour les stocks ou ajoute un relais par adresse. Il peut sélectionner un résultat de recherche puis déplacer le repère pour ajuster l’emplacement.
3. Dans **Préparer une tournée**, il sélectionne les relais, calcule et vérifie le parcours, réordonne les arrêts si nécessaire, nomme la mission et l’attribue à un bénévole.
4. Le bénévole ouvre **Missions**, consulte sa tournée et lance la navigation vers un arrêt. Après la visite, il indique les kilos collectés ou marque l’arrêt comme ignoré. L’avancement de la mission et le stock du relais sont mis à jour.
5. Le coordinateur consulte l’avancement, exporte le CSV ou vérifie le récapitulatif email avant de l’envoyer.

Le bouton d’envoi email n’envoie rien sans une configuration SMTP valide. Les captures montrent uniquement l’aperçu : aucun email de démonstration n’a été envoyé.

### Lancer l’application en local

Python 3.11 ou plus récent est nécessaire. Docker est facultatif pour démarrer l’interface; sans le service de routage, les distances sont calculées à vol d’oiseau et cette limite est signalée dans l’application.

```bash
git clone https://github.com/mouad-abaaqil/Croix-Rouge.git
cd Croix-Rouge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Créez une clé secrète locale, puis initialisez la base et le compte coordinateur :

```bash
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
p.write_text(p.read_text().replace('APP_SECRET_KEY=', f'APP_SECRET_KEY={secrets.token_hex(32)}'))
PY
python3 webapp.py init
python3 webapp.py
```

`init` demande un identifiant et un mot de passe d’au moins 12 caractères. Il charge les points d’exemple à la première initialisation. Ouvrez [http://127.0.0.1:5000](http://127.0.0.1:5000). Si le port est occupé, lancez `PORT=5002 python3 webapp.py` puis ouvrez [http://127.0.0.1:5002](http://127.0.0.1:5002).

### Activer les trajets routiers

Le service OSRM facultatif calcule des distances, durées et tracés à partir du réseau routier. Docker est nécessaire pour cette option. Ajoutez dans `.env` :

```dotenv
ROUTING_URL=http://127.0.0.1:5001
```

Puis préparez la carte régionale et démarrez le service :

```bash
bash scripts/setup_routing.sh
docker compose up -d routing
```

Le téléchargement de la carte fait environ 230 Mo et varie selon la source. Le graphe préparé occupe plusieurs fois cette taille et son pré-calcul peut demander environ 2 Gio de mémoire. Les fichiers restent dans `routing-data/`; le pré-calcul n’est pas répété à chaque lancement. Redémarrez ensuite l’application. OSRM n’intègre pas le trafic en temps réel. OR-Tools Guided Local Search ordonne les arrêts à partir des durées routières; les petites tournées utilisent une optimisation plus légère. Si OSRM est indisponible, l’application revient à une estimation à vol d’oiseau et le signale.

### Configuration disponible

Les valeurs se configurent dans le fichier local `.env` (ignoré par Git). Les identifiants SMTP sont facultatifs; ne les ajoutez jamais au dépôt.

| Variable | Usage |
|:--|:--|
| `APP_SECRET_KEY` | Clé aléatoire utilisée pour signer les sessions |
| `APP_HTTPS` | Mettre à `1` derrière un proxy HTTPS afin d’activer le cookie sécurisé |
| `DATABASE_PATH` | Chemin de la base SQLite; par défaut `instance/redcollect.sqlite3` |
| `ROUTING_URL` | URL du service OSRM; laisser vide pour le calcul de secours |
| `ROUTE_SOLVER_SECONDS` | Temps maximal de recherche OR-Tools, plafonné par l’application |
| `GEOCODER_URL` | Service de recherche d’adresses; Nominatim est utilisé par défaut |
| `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SENDER_EMAIL` | Envoi facultatif des récapitulatifs de mission |

### Cartes, services externes et données

Les tuiles de carte et la recherche d’adresse dépendent d’OpenStreetMap. Une recherche d’adresse est déclenchée par l’utilisateur, limitée à une requête par seconde et mise en cache localement. Avec le service Nominatim public, l’adresse recherchée est envoyée à ce service; cette instance est destinée à un usage modéré. Consultez sa [politique d’utilisation](https://operations.osmfoundation.org/policies/nominatim/) et la [politique des tuiles OpenStreetMap](https://operations.osmfoundation.org/policies/tiles/) avant tout usage. L’application affiche l’attribution OpenStreetMap.

Les points fournis sont des exemples de Calais. Vérifiez et remplacez les adresses, les capacités et les niveaux de stock avant tout usage opérationnel. La base SQLite contient les comptes, points, mises à jour de stock, paramètres et missions de l’installation.

### Limites actuelles

- Aucune instance publique ni aucun compte de démonstration hébergé.
- Pas de trafic routier en direct; les itinéraires sont des estimations.
- Pas de GPS intégré : la navigation ouvre un service externe.
- Les mots de passe des bénévoles sont créés ou réinitialisés par un coordinateur; l’application ne propose pas encore de changement de mot de passe personnel.
- Le journal des stocks est enregistré, mais l’interface ne présente pas encore son historique complet.
- La recherche d’adresse, les tuiles de carte et l’email dépendent des services externes indiqués plus haut.

Pour l’architecture et les évolutions possibles, voir [docs/EVOLUTIONS.md](docs/EVOLUTIONS.md).

### Tests et développement

```bash
python3 -m unittest discover -s tests -v
node --check static/js/app.js
```

Pour comprendre l’application, utilisez la carte du dépôt des fonctionnalités dans [docs/EVOLUTIONS.md](docs/EVOLUTIONS.md), puis lancez les tests avant toute modification.

### Licence et identité

Projet distribué sous licence [MIT](LICENSE). Les marques et emblèmes de la Croix-Rouge restent la propriété de leurs détenteurs respectifs. Ce dépôt est un projet open source indépendant; ne le présentez pas comme un service officiellement exploité par la Croix-Rouge.

---

## English

Red Collect is an open-source web app for coordinating donation collection teams. It puts relay points, stock levels, and collection missions on a map. The interface is available in French and English. There is no hosted public instance; run the app locally from this repository. Screenshots and the silent walkthrough use sample data.

### What each role can do

| Feature | Coordinator | Volunteer |
|:--|:--:|:--:|
| View the dashboard, map, collection points and missions | Yes | Yes |
| Update a point’s stock and record collected kilograms | Yes | Yes |
| Add or edit points, capacities and estimated pickup time | Yes | — |
| Search an address and adjust its map marker | Yes | — |
| Plan a route, reorder stops, create and assign a mission | Yes | — |
| Manage volunteer accounts and depot settings | Yes | — |
| Update stops on an unassigned mission or their own assignment | Yes | Yes* |
| Export a mission as CSV and preview/send its email summary | Yes | CSV export |

\* Volunteers cannot update a mission assigned to another person. Stop navigation opens Google Maps; Red Collect does not provide turn-by-turn GPS navigation.

### Run locally

Use Python 3.11 or newer:

```bash
git clone https://github.com/mouad-abaaqil/Croix-Rouge.git
cd Croix-Rouge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set a random `APP_SECRET_KEY` in `.env`, then run `python3 webapp.py init` and `python3 webapp.py`. Initialization creates the coordinator account and imports sample points into a new database. Open [http://127.0.0.1:5000](http://127.0.0.1:5000). See the French section above for the exact secret-generation command and optional OSRM setup.

### Routing, maps and email

Road routing is optional and uses a local OSRM service with OpenStreetMap data. OR-Tools Guided Local Search optimizes larger tours using OSRM travel times. If OSRM is unavailable, the app labels a straight-line fallback estimate. No live traffic is used. Address search and map tiles use OpenStreetMap services; review their usage policies before running a busy or public instance. Email summaries require SMTP configuration. Preview the message before sending; screenshots never send email.

The sample Calais points are for demonstration only. Verify or replace them before operational use. Current limitations include no hosted demo, no built-in GPS navigation, no volunteer password-change flow, and no stock-history screen.

For setup details, tests, architecture, and a suggested roadmap for future contributions, see the French guide and [docs/EVOLUTIONS.md](docs/EVOLUTIONS.md). The project is distributed under the [MIT License](LICENSE).
