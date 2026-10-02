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
  <img src="assets/redcollect-demo.gif" alt="Démonstration de Red Collect : tableau de bord, recherche d’adresse et itinéraire" width="100%">
</p>

<p align="center"><em>Aucune démo publique hébergée pour le moment : lancez l’application sur votre ordinateur avec les étapes ci-dessous.</em></p>

**Français** · [English](#english)

---

## Français

Red Collect aide une équipe de collecte à voir quels relais nécessitent une visite, à choisir de nouveaux points sur une carte et à organiser les tournées. L’interface est conçue pour être utilisée par un coordinateur et des bénévoles qui ne souhaitent pas manipuler des fichiers CSV ou des coordonnées GPS.

### Aperçu

| Tableau de bord | Points et recherche d’adresse | Préparation d’une tournée |
|:--:|:--:|:--:|
| <img src="assets/screenshots/01-dashboard.png" alt="Tableau de bord avec carte, stocks et points prioritaires" width="320"> | <img src="assets/screenshots/07-address-search.png" alt="Ajout d’un point par recherche d’adresse sur une carte" width="320"> | <img src="assets/screenshots/04-route-preview.png" alt="Ordre optimisé et aperçu d’une tournée routière" width="320"> |

Une vue du tableau de bord en anglais est disponible dans [`assets/screenshots/06-dashboard-en.png`](assets/screenshots/06-dashboard-en.png). Toutes les vues s’adaptent aux écrans mobiles.

### Fonctionnalités

- Carte des relais et indicateurs de remplissage, avec filtres et recherche.
- Ajout d’un relais par recherche d’adresse ou par placement du repère sur la carte ; aucune saisie de latitude ou longitude requise.
- Historique des mises à jour de stock et saisie des quantités collectées.
- Préparation d’une tournée avec réorganisation manuelle des arrêts et estimation de la distance et de la durée.
- Missions attribuables à un bénévole, suivi des arrêts, export CSV et récapitulatif par email facultatif.
- Comptes bénévoles gérés par le coordinateur : création, changement de nom, réinitialisation du mot de passe et suspension/réactivation de l’accès.
- Interface français/anglais, base SQLite locale et données de démonstration.

### Lancer une démo locale

Python 3.11 ou plus récent est nécessaire. Docker est facultatif pour l’interface ; sans moteur routier, l’application affiche une estimation à vol d’oiseau clairement signalée.

```bash
git clone https://github.com/mouad-abaaqil/Croix-Rouge.git
cd Croix-Rouge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Créez une clé de session locale dans `.env`, puis initialisez la base et le compte coordinateur :

```bash
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
p.write_text(p.read_text().replace('APP_SECRET_KEY=', f'APP_SECRET_KEY={secrets.token_hex(32)}'))
PY
python webapp.py init
python webapp.py
```

Ouvrez [http://127.0.0.1:5000](http://127.0.0.1:5000) et connectez-vous avec l’identifiant et le mot de passe choisis pendant `init`. Si le port 5000 est déjà utilisé, lancez `PORT=5002 python webapp.py` et ouvrez [http://127.0.0.1:5002](http://127.0.0.1:5002).

### Activer les trajets routiers

Pour des distances, durées et géométries sur le réseau routier, installez Docker puis décommentez `ROUTING_URL` dans `.env` :

```dotenv
ROUTING_URL=http://127.0.0.1:5001
```

Préparez l’extraction OpenStreetMap du Nord-Pas-de-Calais et démarrez OSRM :

```bash
bash scripts/setup_routing.sh
docker compose up -d routing
```

Le téléchargement initial fait environ 230 Mo ; le graphe préparé occupe davantage de place et le pré-calcul demande environ 2 Gio de mémoire. Cette préparation ne se répète pas à chaque lancement. Redémarrez ensuite `python webapp.py` pour que l’application prenne en compte le service. Les itinéraires routiers restent des estimations : OSRM n’intègre pas le trafic en temps réel. Le projet utilise OR-Tools Guided Local Search pour ordonner plusieurs arrêts à partir de la matrice des durées routières. Si OSRM ne répond pas, l’application conserve un calcul de secours et signale le mode à vol d’oiseau.

### Données cartographiques et de démonstration

Les points et stocks fournis servent à illustrer l’application ; vérifiez les informations et les niveaux de stock avant tout usage opérationnel. La recherche d’adresse est déclenchée par une action explicite, limitée à une requête par seconde et mise en cache. L’instance publique Nominatim est adaptée à un usage modéré seulement : consultez sa [politique d’utilisation](https://operations.osmfoundation.org/policies/nominatim/) avant de l’utiliser et configurez un autre service si le trafic augmente. Les cartes affichent l’attribution OpenStreetMap ; les [règles des tuiles](https://operations.osmfoundation.org/policies/tiles/) s’appliquent aussi.

### Vérification

```bash
python -m unittest discover -s tests -v
node --check static/js/app.js
```

### Licence

Projet distribué sous licence [MIT](LICENSE). Les marques et emblèmes de la Croix-Rouge restent la propriété de leurs détenteurs respectifs.

---

## English

Red Collect is an open-source collection planning app for teams coordinating donation drop-off points. Its French/English interface helps coordinators and volunteers track stock levels, add a relay by searching for an address on the map, plan collection routes, and follow each mission.

**Run it locally:** clone this repository, install the Python requirements, copy `.env.example` to `.env`, set a random `APP_SECRET_KEY`, then run `python webapp.py init` followed by `python webapp.py`. The first command creates the coordinator account and imports the demo points. Open [http://127.0.0.1:5000](http://127.0.0.1:5000). There is no public hosted demo at this time.

For road-based distance and duration estimates, configure the optional self-hosted OSRM service with `scripts/setup_routing.sh`. OR-Tools Guided Local Search optimizes the order of multiple stops using OSRM’s travel-time matrix. Travel times do not include live traffic. See the French sections above for complete setup, map-service policies, and demo-data notes.

The project is released under the [MIT License](LICENSE).
