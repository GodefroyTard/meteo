# Déployer sur un VPS

Guide pas à pas pour un VPS OVH sous Debian ou Ubuntu. Tout tourne dans `docker compose` :
la base, le lot horaire, le serveur web et un proxy qui s'occupe du HTTPS.

```
Internet ──443──> proxy (Caddy) ──> web (meteo servir) ──┐
                                                          ├──> db (PostgreSQL)
                                    lot (cron horaire) ──┘
```

Seul le proxy est exposé. Le site et la base ne sont joignables que depuis le réseau
interne de compose — la base est en plus liée à `127.0.0.1`, parce que **Docker publie ses
ports en contournant le pare-feu** : sans cette précaution elle serait ouverte sur Internet.

## Avant de commencer

Il vous faut :

- un VPS avec un accès SSH et les droits `sudo` ;
- un **nom de domaine** (~10 €/an chez OVH, ou un sous-domaine gratuit type DuckDNS).
  Let's Encrypt ne délivre pas de certificat pour une adresse IP nue : le domaine n'est
  pas optionnel ;
- votre poste de développement avec la base déjà remplie.

## 1. Faire pointer le domaine vers le VPS

Dans la zone DNS de votre domaine, créez un **enregistrement A** :

| Type | Nom | Cible |
|---|---|---|
| A | `meteo` (ou `@` pour le domaine nu) | l'IPv4 de votre VPS |

Comptez de quelques minutes à quelques heures de propagation. Vérifiez depuis votre poste :

```bash
dig +short meteo.mondomaine.fr     # doit renvoyer l'IP du VPS
```

**Ne passez pas à la suite tant que cette commande ne renvoie pas la bonne IP** : Caddy
demandera le certificat au premier démarrage, et Let's Encrypt limite le nombre de
tentatives échouées.

## 2. Redéclarer l'IP auprès d'Infoclimat

C'est l'étape qu'on oublie, et elle casse la collecte en silence.

Le jeton Infoclimat est **lié à une adresse IP déclarée**. Aujourd'hui c'est celle de votre
poste. Depuis le VPS, la collecte des observations échouera tant que la déclaration n'aura
pas changé.

1. Connectez-vous sur [infoclimat.fr/opendata](https://www.infoclimat.fr/opendata/) ;
2. remplacez l'IP déclarée par celle du VPS ;
3. une fois le VPS en service, **arrêtez le lot sur votre poste** — deux machines ne peuvent
   pas utiliser le même jeton :

```bash
docker compose stop lot     # sur le poste de développement
```

Les prévisions Open-Meteo, elles, fonctionnent depuis n'importe où.

## 3. Préparer le VPS

Connectez-vous en SSH, puis installez Docker :

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Déconnectez-vous et reconnectez-vous pour que l'appartenance au groupe `docker` prenne
effet. Vérifiez :

```bash
docker compose version
```

Puis le pare-feu — SSH d'abord, sinon vous vous enfermez dehors :

```bash
sudo apt update && sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp      # nécessaire à la validation Let's Encrypt
sudo ufw allow 443/tcp
sudo ufw enable
```

> `ufw` ne filtre pas les ports publiés par Docker. C'est pour cela que le compose lie la
> base à `127.0.0.1` et n'expose aucun port pour le service `web`. N'ajoutez jamais un
> `ports:` sur ces services sans préfixer par `127.0.0.1:`.

## 4. Déposer le code

Le dépôt n'a pas encore de remote : le plus simple est de synchroniser le dossier depuis
votre poste.

```bash
# depuis le poste de développement, à la racine du projet
rsync -av --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.env' --exclude '*.dump' --exclude '.pytest_cache' --exclude '.ruff_cache' \
  ./ utilisateur@IP_DU_VPS:~/meteo/
```

Le `.env` est volontairement exclu : il contient votre jeton, et sa valeur `METEO_DSN`
n'est pas la bonne pour le VPS. On le crée à la main juste après.

*Plus tard :* pousser le projet sur un dépôt Git privé rendra les mises à jour plus
propres (`git pull` au lieu d'un `rsync`).

## 5. Écrire le `.env` du VPS

Sur le VPS :

```bash
cd ~/meteo
cp .env.example .env
nano .env
```

Renseignez :

```ini
METEO_JETON_INFOCLIMAT=votre-jeton
COMPOSE_PROFILES=vps
METEO_DOMAINE=meteo.mondomaine.fr
METEO_MDP_BASE=un-mot-de-passe-long-et-unique
```

- `COMPOSE_PROFILES=vps` est ce qui active les services `web` et `proxy`. Sans cette ligne,
  `docker compose up -d` ne démarrerait que la base et le lot.
- `METEO_MDP_BASE` n'est pris en compte **qu'à la première création du volume**. Le changer
  ensuite n'a aucun effet : il faudrait supprimer le volume, donc les données.
- Laissez `METEO_DSN` tel quel : le compose le réécrit pour les conteneurs.

## 6. Transférer la base

Refaire le backfill sur le VPS prendrait environ deux heures et infligerait deux ans et demi
de requêtes à une association de bénévoles. Le dump compressé pèse **17 Mo** : transférez-le.

```bash
# sur le poste de développement
docker compose exec -T db pg_dump -U meteo -Fc meteo > meteo.dump
scp meteo.dump utilisateur@IP_DU_VPS:~/meteo/
```

```bash
# sur le VPS
cd ~/meteo
docker compose up -d db
docker compose exec -T db pg_restore -U meteo -d meteo --clean --if-exists < meteo.dump
```

Quelques avertissements « does not exist, skipping » au premier passage sont normaux : la
base est vide, il n'y a rien à nettoyer.

Vérifiez :

```bash
docker compose exec -T db psql -U meteo -c "SELECT count(*) FROM observation;"
```

## 7. Démarrer

```bash
cd ~/meteo
docker compose up -d --build
```

Le premier démarrage construit l'image (quelques minutes) puis Caddy demande le certificat.

## 8. Vérifier

```bash
docker compose ps                                    # les 4 services « Up »
docker compose logs proxy | grep -i certificate      # « certificate obtained successfully »
curl -I https://meteo.mondomaine.fr                  # HTTP/2 200
docker compose logs lot                              # « Lot planifié en place »
```

Ouvrez le site dans un navigateur. Le cadenas doit apparaître, et le bouton **« Utiliser ma
position »** doit fonctionner — c'est précisément ce que le HTTPS rend possible.

Attendez le prochain passage du lot (minute 17 de chaque heure) et contrôlez :

```bash
docker compose logs lot --tail 20
```

Vous devez lire une ligne du type « 1 234 prévisions et 56 observations collectées ». **Si le
nombre d'observations est nul ou si la commande échoue, l'IP n'est pas déclarée chez
Infoclimat** — retour à l'étape 2.

## Au quotidien

**Suivre les journaux**

```bash
docker compose logs -f lot      # le lot horaire
docker compose logs -f web      # les requêtes du site
docker compose logs -f proxy    # le certificat, les erreurs d'accès
```

**Déployer une modification**

```bash
# depuis le poste : le rsync de l'étape 4, puis sur le VPS
docker compose up -d --build
```

**Sauvegarder la base**

Le dump est petit ; une sauvegarde quotidienne coûte peu. Sur le VPS, dans `crontab -e` :

```
30 3 * * * cd ~/meteo && docker compose exec -T db pg_dump -U meteo -Fc meteo > ~/sauvegardes/meteo-$(date +\%F).dump
```

Pensez à `mkdir -p ~/sauvegardes` et à purger les vieux fichiers.

**Changer la cadence du lot**

Modifiez [docker/crontab](../docker/crontab), puis reconstruisez :

```bash
docker compose up -d --build lot
```

## Si ça coince

| Symptôme | Cause la plus probable |
|---|---|
| Caddy ne décroche pas de certificat | le domaine ne pointe pas encore sur le VPS, ou le port 80 est fermé |
| Le site répond mais pas en HTTPS | `METEO_DOMAINE` absent du `.env` : Caddy est retombé sur `localhost` |
| Aucune observation collectée | l'IP du VPS n'est pas déclarée chez Infoclimat |
| Le lot échoue avec une erreur de connexion | `METEO_DSN` a été forcé dans le `.env` ; laissez le compose le définir |
| `docker compose up` ne démarre que 2 services | `COMPOSE_PROFILES=vps` manque dans le `.env` |
| Le site est inaccessible depuis l'extérieur | `sudo ufw status` — 80 et 443 doivent être autorisés |
