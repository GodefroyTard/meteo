# Fiabilité des modèles météo

Pour un lieu donné, quel modèle de prévision se trompe le moins — mesuré en confrontant
ce que chaque modèle annonçait à ce que les stations ont réellement mesuré.

Périmètre initial : les stations du réseau participatif StatIC autour de Grenoble, dont
l'étagement de 220 m à 1965 m sur une vingtaine de kilomètres fait tout l'intérêt.

- [CONTEXT.md](CONTEXT.md) — le vocabulaire du domaine. À lire en premier.
- [docs/adr/](docs/adr/) — les décisions structurantes et leurs raisons.
- [docs/deploiement.md](docs/deploiement.md) — mise en production sur un VPS, pas à pas.

## Mise en route

```bash
uv sync
cp .env.example .env          # renseigner METEO_JETON_INFOCLIMAT
docker compose up -d

uv run meteo init-base        # crée les tables
uv run meteo stations         # importe le référentiel StatIC, fixe le périmètre
uv run meteo previsions       # backfill Open-Meteo (long : ~2 h sur 2 ans et demi)
uv run meteo observations     # backfill Infoclimat — voir la contrainte d'IP ci-dessous
uv run meteo verdicts         # recalcule tout et remplace la table
uv run meteo climatologie     # séries longues Météo-France (~2 min, aucun jeton)
uv run meteo servir           # http://127.0.0.1:8000
```

## Mise à jour planifiée

Une fois le backfill initial passé, la mise à jour tourne toute seule : le service `lot`
de `docker compose` exécute `meteo rafraichir` chaque heure (cadence dans
[docker/crontab](docker/crontab)).

```bash
docker compose up -d           # lance la base et le lot
docker compose logs -f lot     # suit les passages
```

`meteo rafraichir` ne recollecte que les **trois derniers jours** puis recalcule les
verdicts. C'est ce qui la rend planifiable — et c'est aussi le piège à éviter :

> `meteo previsions` et `meteo observations` **sans bornes repartent de
> `METEO_DEBUT_HISTORIQUE`**, soit plusieurs heures de collecte. Ne les mettez jamais dans
> un cron.

Trois points d'exploitation :

- le conteneur reçoit sa configuration par `env_file: .env`, mais `METEO_DSN` est
  **réécrit dans le compose** : dans le réseau interne la base répond sur `db:5432`, pas
  sur `localhost:5433` ;
- cron ne transmet pas l'environnement du conteneur à ses tâches. `docker/demarrer.sh` le
  dépose dans `/app/env.sh`, que la tâche recharge ;
- si Infoclimat échoue, le passage s'arrête avant le recalcul et sort en erreur dans
  `docker compose logs`. C'est voulu : un échec doit se voir. Les verdicts ne bougeant que
  lorsque de nouvelles observations arrivent, rien n'est perdu au passage suivant.

L'interface n'a plus de bouton « rafraîchir » : elle affiche la date du dernier passage.
Exposer le déclencheur à tout visiteur revenait à confier le quota d'une association de
bénévoles à des inconnus. Les routes `POST /api/rafraichir` et `GET /api/rafraichissement`
restent disponibles pour un déclenchement manuel, avec leur garde-fou de 30 minutes.

## Les trois sources

**Open-Meteo** fournit les prévisions, y compris *les runs passés* : c'est ce qui permet
de calculer des statistiques rétroactivement au lieu d'attendre des mois de collecte.
L'archive démarre le 20/01/2024 (AROME, ICON-D2) et le 04/02/2024 (ECMWF).

**Infoclimat** fournit les observations, via le réseau participatif StatIC.

Pour obtenir le jeton : créer un compte sur
[infoclimat.fr](https://www.infoclimat.fr/include/inscription.php), puis retourner sur
[la page opendata](https://www.infoclimat.fr/opendata/) — l'interface de génération de
clés n'apparaît qu'une fois connecté, et liste les clés existantes.

Le formulaire demande de déclarer un usage **commercial ou non commercial**, et ce choix
filtre les stations accessibles. Sur les 7 stations du périmètre grenoblois, 3 sont en
licence CC BY-NC : Saint-Martin-d'Hères, Lans – Les Allières et Saint-Pancrasse. Déclarer
un usage commercial les retire, et avec Saint-Martin-d'Hères disparaît la seule station de
fond de vallée — il ne resterait que du plateau entre 900 et 1000 m.

Trois contraintes à connaître ensuite :

- le jeton est **lié à une adresse IP déclarée** — le backfill des observations ne
  fonctionne que depuis la machine déclarée, en pratique le VPS et non le poste de dev ;
- 7 jours consécutifs au maximum par requête, moins d'une requête par seconde ;
- attribution obligatoire : le lien vers infoclimat.fr est dans le pied de page du front.

C'est une association de bénévoles qui offre ce service gratuitement. Le client respecte
ces limites, ne les desserrez pas.

**Météo-France** fournit les séries longues, par le jeu « Données climatologiques de base -
quotidiennes » publié sur [meteo.data.gouv.fr](https://meteo.data.gouv.fr/) sous licence
ouverte LOV2. Deux fichiers par département, sans jeton ni quota : le socle
température-pluie et l'évapotranspiration potentielle. L'Isère entière pèse 25 Mo
compressés, remonte à 1950 — parfois bien avant — et donne 3 millions de journées pour
208 postes : températures, pluie, évapotranspiration et hauteur de neige.

Ces données alimentent la seule page climat et **n'entrent jamais dans un verdict** : un
maximum quotidien n'est pas comparable à une prévision horaire, et les postes ne sont pas
là où sont les stations. Voir [ADR 0008](docs/adr/0008-la-serie-longue-ne-juge-aucun-modele.md).

## Organisation du code

```
src/meteo/
  domaine/      logique pure — aucune E/S, entièrement testable
  stockage/     schéma et session SQLAlchemy
  collecte/     clients HTTP Open-Meteo, Infoclimat et Météo-France
  lots/         traitements par lot : référentiel, backfill, calcul des verdicts
  api/          FastAPI, lecture seule sur les verdicts matérialisés
  web/          gabarits, feuilles de style, icônes du Temps et tracé SVG du front
```

Le calcul lourd vit dans `lots/`, l'API ne fait que lire (voir
[ADR 0004](docs/adr/0004-verdicts-materialises-par-lot.md)).

Le front expose deux pages sous un menu latéral commun (`web/templates/_base.html`) :

| Route | Page | Ce qu'elle répond |
|---|---|---|
| `/` | Prévision météo | quel temps il fait et ce qu'annonce chacun des six modèles |
| `/fiabilite` | Fiabilité des modèles | lequel se trompe le moins ici, et sur quelles mesures |

Le menu porte ce qui vaut pour les deux — le lieu — et chaque page garde ses propres
réglages. Le lieu se transporte d'une page à l'autre dans l'URL ; changer de station depuis
le menu ne réinitialise pas les réglages de la page en cours.

Le modèle mis en avant sur la page de prévision est celui que désigne le verdict à un jour
d'échéance, sur la température, dans la saison en cours (`ANTICIPATION_CONSEIL` dans
`api/app.py`) : c'est la question qu'on se pose en regardant la météo. Les autres
combinaisons appartiennent à la page de fiabilité.

La page de prévision porte aussi neuf indications qui ne jugent aucun modèle
(`domaine/conditions.py`), en trois panneaux de trois cellules : ce que ça fait dehors
(ressenti, vent, humidité), le ciel (indice UV, soleil, isotherme 0 °C), ce qui situe la
journée (écart à la moyenne, pression, qualité de l'air). Chaque cellule porte la teinte de
son état — c'est la troisième et dernière signification de la couleur sur le site, encadrée
par l'[ADR 0007](docs/adr/0007-le-ciel-se-colore-du-temps-pas-du-modele.md).

Chacune vient du modèle qui porte déjà la bande de ciel, ou — pour celles qu'il n'annonce
pas — du premier qui les annonce, et le bloc le nomme. Ce qu'il faut savoir :

- **AROME ne publie ni pression ni isotherme 0 °C** ; **seul GFS publie l'indice UV**. Les
  emprunts sont donc la règle plutôt que l'exception, et toujours attribués.
- La **pression est ramenée au niveau de la mer** : à 905 m la pression réelle tourne autour
  de 916 hPa, ce qui se ferait relire. C'est la tendance sur trois heures qui informe.
- L'**isotherme 0 °C** n'est pas converti en limite pluie-neige : celle-ci se situe quelques
  centaines de mètres plus bas, mais de combien dépend de l'intensité des précipitations.
- La **qualité de l'air** vient d'un service distinct (analyse européenne CAMS,
  `air-quality-api.open-meteo.com`) qui ne se décline pas par modèle. Son indisponibilité
  n'emporte pas la page.
- La **« moyenne »** est celle des Observations de la station elle-même sur les années
  disponibles, pas une normale climatique (voir `Moyenne mesurée` dans
  [CONTEXT.md](CONTEXT.md)). Aucune réanalyse n'y entre : une moyenne de grille à 25 km ne
  dirait rien d'un fond de vallée à 220 m.

Le style vit dans `web/static/page.css` (les deux pages) et `web/static/viz.{css,js}` (le
graphe). Deux jeux de couleurs y cohabitent sans jamais se croiser — le ciel suit le Temps,
les repères suivent le Modèle (voir
[ADR 0007](docs/adr/0007-le-ciel-se-colore-du-temps-pas-du-modele.md)).

## Points ouverts

- **Seuil de pluie** : fixé provisoirement à 0,2 mm/h dans `domaine/verdict.py`. À 0,1 mm
  on compte la bruine, à 1 mm on ignore ce que les gens appellent de la pluie.
- **Neige** : les pluviomètres à auget ne la captent pas. En altitude et en hiver, la
  variable pluie sera à désactiver station par station — le découpage par saison le permet
  déjà, la règle reste à écrire.
- **Exposition du service sur le VPS** — le serveur web tourne encore sur l'hôte
  (`uv run meteo servir`), seul le lot est conteneurisé.
