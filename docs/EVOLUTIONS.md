# Architecture et pistes d’évolution

Ce document décrit le code actuel et propose un chemin de développement pour les prochaines contributions. Il reflète l’implémentation présente dans le dépôt; ce n’est pas une promesse de fonctionnalité.

## Carte du code

| Chemin | Responsabilité |
|:--|:--|
| `webapp.py` | Routes Flask, sessions, autorisations, validation des entrées, API JSON, génération CSV et envoi email |
| `database.py` | Schéma SQLite, initialisation, petites migrations, lecture des points et du dépôt |
| `routing.py` | Validation géographique, matrice des durées, optimisation de séquence, appels OSRM et calcul de secours |
| `analytics.py` | Agrégats temporels de remplissage, pression récurrente, collectes et clusters de relais proches |
| `templates/` | Squelettes HTML des pages et des dialogues |
| `static/js/app.js` | Traductions FR/EN, appels API, interactions, cartes Leaflet et rendu des pages |
| `static/css/app.css` | Présentation et mise en page de l’interface |
| `data/collection_points.csv` | Données d’exemple importées à l’initialisation d’une base vide |
| `scripts/setup_routing.sh` | Téléchargement et pré-calcul du graphe OSRM régional |
| `docker-compose.yml`, `Dockerfile` | Services conteneurisés pour une installation auto-hébergée ultérieure |
| `tests/` | Tests unitaires d’analyse/routage et tests Flask/API sur des bases temporaires |

La base SQLite par défaut se trouve dans `instance/redcollect.sqlite3`. Tables principales : `local_units`, `unit_settings`, `users`, `settings`, `points`, `stock_history`, `geocode_cache`, `missions` et `mission_stops`. Les utilisateurs, points et missions portent un `unit_id`; les lectures et écritures applicatives sont filtrées par unité. Les migrations actuelles ajoutent des colonnes/tables manquantes; elles ne remplacent pas un mécanisme de migration versionné si le schéma évolue beaucoup.

`data/local_units.json` contient l’index des URLs `/unite-locale-` du sitemap officiel, extrait le 3 octobre 2026. Les noms sont générés à partir des slugs, sans adresse postale; utiliser le lien officiel pour vérifier l’intitulé courant. `scripts/update_local_units.py` actualise cette source sur demande. Le site ne fournissant pas de licence ouverte clairement identifiable, vérifier les conditions de réutilisation avant de republier une copie de l’annuaire.

## Rôles et autorisations actuels

- **Coordinateur** : s’inscrit depuis l’accueil en choisissant une unité; crée les bénévoles de cette unité, modifie les coordonnées de l’équipe, réinitialise les mots de passe ou suspend l’accès; règle le dépôt; gère les points et missions.
- **Bénévole** : consulte les données de son unité, modifie son profil, met à jour les stocks et les arrêts des missions affectées à son compte.
- Les mutations API utilisent un jeton CSRF et les mots de passe sont hachés. Le dernier coordinateur ne peut pas être désactivé.
- La page d’analyse et son API sont réservées au coordinateur.
- Les coordinateurs s’inscrivent depuis l’accueil; les bénévoles sont créés par un coordinateur et rattachés automatiquement à son unité. Il n’y a pas encore de changement de mot de passe personnel ni de procédure de réinitialisation par email.
- L’API sait marquer un point inactif, mais l’interface ne propose pas encore de commande pour changer son état.

Une évolution du modèle de droits devrait mettre à jour ensemble les décorateurs Flask, les contrôles visibles dans l’interface et les tests d’accès pour chaque rôle.

## Calcul des tournées

1. `routing.py` valide les coordonnées, identifiants et durées de service.
2. Si `ROUTING_URL` pointe vers OSRM, l’application demande la matrice de distances/durées et le tracé routier détaillé.
3. Le coordinateur peut conserver l’ordre manuel. Sinon une heuristique de voisin le plus proche suivie d’un 2-opt traite les petites tournées; OR-Tools Guided Local Search est employé pour les tournées plus grandes.
4. En cas de panne OSRM, la distance et la durée indicative utilisent la distance à vol d’oiseau. L’interface annonce ce mode dégradé.
5. Les temps n’incluent pas le trafic en direct. La durée totale ajoute le temps estimé passé à chaque point.

Pour remplacer ou améliorer l’optimiseur, conserver les invariants existants : visite de chaque arrêt une fois, départ et retour au dépôt, ordre manuel respecté, gestion des sens uniques avec une matrice dirigée, durée de calcul bornée, et solution explicite de secours. Ajouter des cas de tests sur matrices et petites instances de référence avant de modifier l’algorithme.

## Analyse du réseau

`/api/analytics?days=30|90|180|365` agrège les entrées `stock_history` et les arrêts de mission terminés dans la période. Les séries de remplissage utilisent uniquement les relevés explicitement enregistrés; les stocks de démonstration et les valeurs actuelles non observées ne sont pas traités comme de l’historique. Les arrêts terminés donnent séparément le nombre de visites et les kilos collectés.

Les fenêtres disponibles sont 30, 90, 180 et 365 jours. Une pression répétée au niveau d’un point exige au moins quatre relevés sur une période d’au moins quatorze jours, une moyenne de remplissage d’au moins 70 % et au moins 50 % des relevés au seuil urgent actuel de 80 %. Un secteur à étudier exige au moins six relevés, quatorze jours d’étendue, une moyenne d’au moins 70 % et un taux de relevés urgents d’au moins 50 %. La page montre également une moyenne hebdomadaire, les parts de relevés urgents par jour de semaine, le volume collecté, une carte, le stock actuel par catégorie de dons et une comparaison descriptive des collectes sur deux périodes successives de même durée. Cette comparaison n’établit pas que le logiciel a causé une évolution.

Les familles de dons proposées sont vêtements, chaussures, hygiène, bébé et puériculture, linge de maison, alimentation, autres dons et non classés. Chaque point dispose d’un inventaire ventilé; le total doit rester inférieur à sa capacité. Lors de la clôture d’un arrêt, le bénévole peut répartir les kilos par catégorie. Les anciennes quantités agrégées sont migrées vers « non classés » pour ne pas attribuer de type inventé. Les collectes par catégorie ne peuvent donc être comparées qu’à partir de l’activation de cette fonction.

Les secteurs sont des composantes de points séparés par moins de 1,5 km; ils ne sont ni des quartiers officiels, ni une couverture de population. La recommandation signifie « examiner la possibilité d’un relais complémentaire », pas « construire un locker ». Le système ne connaît pas les dépôts manqués, les personnes qui renoncent, les volumes de dons non enregistrés, les coûts ou la capacité de nouveaux emplacements. Le tableau de bord ne peut donc pas encore mesurer la demande dans une zone sans point existant ni prévoir le nombre de tournées évitées.

## Configuration et exécution

La configuration locale se fait dans `.env`; ne jamais commiter ce fichier ni une vraie base de données. Variables prises en charge :

- `APP_SECRET_KEY`, `APP_HTTPS` pour les sessions et cookies.
- `DATABASE_PATH` pour choisir la base SQLite.
- `ROUTING_URL`, `ROUTE_SOLVER_SECONDS` pour le routage.
- `GEOCODER_URL` pour le service de recherche d’adresses.
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SENDER_EMAIL` pour les récapitulatifs.

Installation de développement :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 webapp.py init
python3 -m unittest discover -s tests -v
node --check static/js/app.js
```

Pour les captures ou essais contrôlés, utiliser `DATABASE_PATH` vers une base temporaire. Éviter de préparer des données de présentation dans la base SQLite personnelle.

## Feuille de route suggérée

### Prochaines améliorations pour les équipes

- Afficher l’historique des stocks par point avec date, auteur et évolution.
- Enregistrer des relevés réguliers ou définir un rappel de contrôle, pour rendre les comparaisons par jour de semaine plus représentatives.
- Ajouter des limites de quartiers configurables, de la densité de population ou des signalements de dépôts/refus pour étudier les zones sans point existant.
- Mesurer le nombre de tournées urgentes et leur coût, puis comparer ces indicateurs avant/après l’ouverture d’un relais.
- Permettre au bénévole de changer son propre mot de passe et donner un flux de réinitialisation sûr.
- Ajouter des notes, pièces jointes légères et consignes par point ou mission, avec horodatage et auteur.
- Ajouter une vue de planification des missions par date et disponibilité des bénévoles.
- Rendre plus visibles les états actif/inactif des points et permettre leur gestion dans l’interface.

### Fiabilisation avant un usage opérationnel

- Choisir et documenter le fournisseur de géocodage/tuiles selon le volume, la confidentialité et les conditions d’utilisation.
- Ajouter une sauvegarde/restauration testée de SQLite et un guide de mise à jour/migration.
- Compléter les tests par des parcours navigateur couvrant coordinateur et bénévole, y compris les erreurs réseau.
- Ajouter une configuration de journalisation exploitable et des contrôles de santé pour Flask et OSRM.
- Préparer un guide d’installation HTTPS derrière un proxy inverse, de gestion des secrets et de mise à jour des données cartographiques.

### Changements d’architecture à décider selon le contexte

- Garder SQLite pour une petite équipe ou migrer vers PostgreSQL si l’usage concurrent augmente.
- Remplacer les migrations opportunistes par Alembic ou un mécanisme versionné avant que le schéma multi-unité ne s’étende.
- Décider si l’envoi email reste une fonctionnalité SMTP simple ou si un service de notifications est nécessaire.
- Évaluer une application mobile/PWA seulement si le mode hors connexion ou le travail terrain le justifie.

## Avant d’ouvrir une pull request

1. Décrire le problème utilisateur et le rôle concerné.
2. Vérifier les droits côté serveur; cacher un bouton ne remplace pas une autorisation API.
3. Ajouter ou adapter un test significatif dans `tests/`.
4. Lancer la suite Python et vérifier `static/js/app.js` avec Node.
5. Si l’interface change, capturer les écrans touchés sur une base temporaire et vérifier le français comme l’anglais.
6. Ne pas inclure `.env`, `instance/`, `routing-data/`, des identifiants ou des données personnelles dans le commit.
