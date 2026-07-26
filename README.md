# telegram-tech-bot

Bot Telegram autonome qui publie chaque jour, sans intervention manuelle :

- un post culture générale informatique (astuces, cybersécurité, dev, systèmes, DevOps, cloud, IA) ;
- un digest des actualités IT du jour, agrégées depuis plusieurs flux RSS ;
- 10 questions de quiz de programmation sur **un thème unique tiré au sort chaque jour** (anti-répétition sur 14 jours), réparties en 3 faciles / 5 intermédiaires / 2 difficiles, publiées en rafale espacée. Les questions qui s'appuient sur un extrait de code sont illustrées par une image générée automatiquement (repli en texte si le service d'image est indisponible).

Tout le contenu est généré par **Claude Code** (le CLI, en mode non interactif), via la session déjà authentifiée sur ce serveur — pas d'appel API externe facturé séparément.

## Sommaire

- [Architecture](#architecture)
- [Déroulement d'une journée](#déroulement-dune-journée)
- [Prérequis](#prérequis)
- [Configuration (.env)](#configuration-env)
- [Déploiement](#déploiement)
- [Développement et tests](#développement-et-tests)
- [Persistance (SQLite)](#persistance-sqlite)
- [Sauvegardes et supervision](#sauvegardes-et-supervision)
- [Logs](#logs)
- [Sécurité](#sécurité)
- [Structure du dépôt](#structure-du-dépôt)

## Architecture

```
app/
  core/          configuration, logging, scheduler, taxonomie d'erreurs
  publishing/     tout ce qui parle à l'API Telegram
  generation/     tout ce qui parle à Claude Code (client + prompts + generators)
  news/           agrégation RSS + déduplication
  persistence/    schéma et requêtes SQLite
  jobs/           orchestration d'une journée (assemble tout ce qui précède)
  main.py         point d'entrée : démarre le scheduler, tourne indéfiniment
```

Chaque package a une seule responsabilité et ne connaît que ce dont il a besoin :

| Package | Rôle | Ne connaît pas |
|---|---|---|
| `core` | config typée (fail-fast), logs, scheduler APScheduler, exceptions | rien de métier — dépendance de tout le reste |
| `publishing` | dispatch des 4 types de contenu (`SimpleMessage`, `Quiz`, `Image`, `ImagePoll`) vers l'API Telegram, retry réseau | Claude Code, SQLite |
| `generation` | construit les prompts, appelle `claude -p`, valide/parse la sortie en objets `publishing.content_models` | l'API Telegram |
| `news` | fetch + normalisation des flux RSS, filtre de déduplication | Claude Code (le choix éditorial se fait dans `generation.news_generator`) |
| `persistence` | seule source de vérité sur "ce qui a déjà été publié" | logique métier — expose juste des requêtes |
| `jobs` | orchestre : idempotence, retry, gestion d'erreurs, alerte admin | rien de nouveau — assemble les couches ci-dessus |

Le contrat de contenu (`app/publishing/content_models.py`) est le point de passage obligé entre génération et publication : que le texte vienne d'un humain ou de Claude, il est validé (longueur, cohérence `correct_answer`/`options`, limites de l'API Telegram) **avant** tout envoi. Un quiz dont la bonne réponse ne correspond à aucune option, ou dont l'explication dépasse 200 caractères, est rejeté à la construction de l'objet, pas découvert en pleine nuit dans un log d'erreur Telegram.

## Déroulement d'une journée

Trois jobs indépendants, planifiés par un scheduler interne (APScheduler, cron) — pas de cron système, pas d'Airflow : le besoin réel (3 tâches/jour) ne justifie pas un orchestrateur de DAG.

| Job | Horaire par défaut | Étapes |
|---|---|---|
| `tech_post` | 08:00 | génère un post (thèmes récents exclus), valide, publie |
| `news_digest` | 08:15 | agrège les flux RSS, déduplique, Claude sélectionne+rédige un digest à partir des articles nouveaux, publie |
| `quiz` | 12:30 | tire un thème unique au sort pour la journée (anti-répétition 14 jours), génère et publie 10 questions dessus selon un plan de difficulté fixe (3 faciles / 5 intermédiaires / 2 difficiles), à la suite, espacées de 8s |

Chaque job est **idempotent indépendamment** : `run_log.steps_completed` (table SQLite) garde la trace de ce qui a déjà été publié aujourd'hui. Si le conteneur redémarre en cours de journée (crash, `docker compose restart`), le job déjà exécuté est sauté au lieu d'être republié. Le quiz va plus loin : le thème du jour est figé dès le premier tirage (table `daily_quiz_theme`), et l'idempotence se fait **par position dans le plan de difficulté** (`count_quiz_published_today`) — si le conteneur crashe après la 4ᵉ question sur 10, un redémarrage reprend exactement à la 5ᵉ plutôt que de tout republier ou de tout resauter. L'échec d'une question (génération ou envoi) n'empêche jamais les suivantes de partir.

**Questions avec code** — si une question s'appuie sur un extrait de code, Claude le fournit séparément (`code`/`language`, jamais dans le texte de la question). Le code est envoyé à un service de rendu externe (`CODE_IMAGE_API_URL`) qui renvoie une image, publiée en photo juste avant le poll. Si ce service échoue (indisponible, timeout), le code est réintégré dans le texte de la question, tronqué pour respecter la limite de 300 caractères de l'API Telegram — le quiz est toujours publié, jamais perdu.

Testé en conditions réelles : 10/10 questions publiées sur un thème unique, répartition de difficulté exacte confirmée, questions à code illustrées par une image générée avec succès.

Politique d'erreurs (`app/jobs/daily_run.py::_generate_with_recovery`) :

- **timeout Claude** ou **sortie invalide** → une tentative de récupération, puis abandon du job du jour (loggé dans `generation_errors`, les deux autres jobs ne sont pas affectés) ;
- **erreur CLI franche** (non connecté, rate-limit) → jamais retentée à l'aveugle, alerte immédiate (email + Telegram admin, voir [Sauvegardes et supervision](#sauvegardes-et-supervision)).

Un flux RSS injoignable est ignoré (loggé) sans bloquer les autres.

## Prérequis

- **Claude Code doit être connecté sur l'hôte** (`claude /login`, interactif, une seule fois). Sans ça, `claude -p` renvoie `Not logged in` et tous les jobs de génération échouent. Vérifier : `claude -p "ping" --output-format text` en SSH sur le serveur.
- Docker + Docker Compose (déjà présents sur ce serveur).
- Un bot Telegram (token via [@BotFather](https://t.me/BotFather)) ajouté comme administrateur du canal cible.

## Configuration (`.env`)

Copier `.env.example` vers `.env` et renseigner :

| Variable | Rôle |
|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | obligatoires — bot et canal de publication |
| `TELEGRAM_ADMIN_CHAT_ID` | optionnel — canal Telegram recevant les alertes d'échec |
| `TZ` | fuseau utilisé par le scheduler (défaut `Europe/Paris`) |
| `SCHEDULE_TECH_POST_CRON`, `SCHEDULE_NEWS_CRON`, `SCHEDULE_QUIZ_CRON`, `SCHEDULE_BACKUP_CRON` | horaires (cron 5 champs) |
| `CLAUDE_BINARY_PATH`, `CLAUDE_TIMEOUT_SECONDS` | binaire `claude` et timeout par appel |
| `APP_UID`, `APP_GID` | UID/GID de build de l'image — **doivent matcher l'utilisateur hôte** (voir Sécurité) |
| `CLAUDE_HOST_HOME` | home hôte contenant la session Claude Code à bind-monter |
| `RESEND_API_KEY`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO` | optionnel — alerte email (Resend) sur échec définitif de génération |
| `UPTIME_KUMA_PUSH_URL`, `HEARTBEAT_INTERVAL_SECONDS` | optionnel — heartbeat vers un moniteur Uptime Kuma de type Push (défaut 300s) |
| `CODE_IMAGE_API_URL`, `CODE_IMAGE_TIMEOUT_SECONDS` | service de rendu de code en image pour les questions de quiz avec code |

`config/quiz_themes.yaml` (liste des thèmes de quiz) et `config/news_sources.yaml` (flux RSS) sont éditables sans rebuild — montés en volume, pas copiés dans l'image.

## Déploiement

```bash
cd /opt/docker/telegram-tech-bot
docker compose build
docker compose up -d
docker compose logs -f
```

`restart: unless-stopped` prend en charge le redémarrage automatique après reboot du serveur (via `dockerd`, lancé au démarrage par systemd).

Mise à jour : `git pull` puis `docker compose build --pull && docker compose up -d`. Pas de mise à jour automatique (pas de Watchtower) — un changement de logique de génération ne doit jamais arriver sans revue.

## Développement et tests

Il n'y a pas de suite de tests automatisée classique : chaque brique a été validée par un **smoke test qui exerce le vrai comportement** (appel Claude réel, envoi Telegram réel sur un canal de test, vraies requêtes SQLite), pas des mocks. Ces scripts vivent dans `scripts/` et **ne sont pas inclus dans l'image de production** (`.dockerignore`).

```bash
# Valide la config sans rien envoyer
docker compose run --rm telegram-tech-bot python -m app.main --dry-run

# Exécuté depuis une image de dev (scripts montés), pas l'image de prod :
docker run --rm -v "$(pwd)":/app -w /app --env-file .env \
  -e HOME=/home/franck -e PATH="/home/franck/.local/bin:$PATH" \
  -v /home/franck/.claude.json:/home/franck/.claude.json \
  -v /home/franck/.claude:/home/franck/.claude \
  -v /home/franck/.local/bin:/home/franck/.local/bin:ro \
  -v /home/franck/.local/share/claude:/home/franck/.local/share/claude \
  -v /home/franck/.local/state/claude:/home/franck/.local/state/claude \
  -v /home/franck/.cache/claude:/home/franck/.cache/claude \
  python:3.12-slim bash -c "pip install -q -r requirements.txt && python -m scripts.smoke_test_daily_run"
```

Scripts disponibles : `smoke_test_publisher` (couche Telegram), `smoke_test_db` (persistance/idempotence), `smoke_test_generation` (Claude → validation → publication), `smoke_test_news` (agrégation/dédup RSS), `smoke_test_daily_run` (orchestration complète), `smoke_test_scheduler` (câblage APScheduler).

## Persistance (SQLite)

Un seul fichier, `data/app.db`, mode WAL. Choisi plutôt que Postgres : usage mono-écrivain, quelques lignes par jour — un SGBD serveur séparé (volume, sauvegarde, identifiants dédiés) serait disproportionné.

| Table | Rôle |
|---|---|
| `published_items` | tout contenu publié (type, thème, texte, `message_id` Telegram) — alimente la déduplication (par thème pour les quiz, globale pour le reste) |
| `news_seen` | registre des articles RSS déjà vus (par hash d'URL) |
| `generation_errors` | journal des échecs de génération, par étape et catégorie d'erreur |
| `run_log` | idempotence quotidienne (`steps_completed` par date) |
| `daily_quiz_theme` | thème de quiz tiré au sort pour chaque jour, figé dès le premier tirage |

## Sauvegardes et supervision

**Sauvegardes** — `run_backup_step` (03:00 par défaut) fait un `VACUUM INTO` de `data/app.db` vers `backups/app-YYYY-MM-DD.db` (cohérent même si l'appli écrit en même temps, contrairement à une copie de fichier brute), puis purge au-delà de 14 jours. Restauration = copier le fichier voulu vers `data/app.db`, aucun outillage dump/restore nécessaire.

**Alertes** — sur échec définitif d'un job (`_alert_admin` dans `daily_run.py`), les canaux configurés sont sollicités en parallèle, aucun n'est requis pour que l'autre fonctionne :
- email via [Resend](https://resend.com) (`RESEND_API_KEY`/`ALERT_EMAIL_TO`) — indépendant de Telegram, donc utile même si le problème vient de Telegram lui-même ;
- message Telegram vers `TELEGRAM_ADMIN_CHAT_ID`.

Si aucun des deux n'est configuré, l'échec est simplement loggé (`generation_errors` + un `WARNING` explicite) — jamais silencieux, mais jamais bloquant non plus.

**Heartbeat Uptime Kuma** — si `UPTIME_KUMA_PUSH_URL` est renseignée, un ping est envoyé toutes les `HEARTBEAT_INTERVAL_SECONDS` (300s par défaut) vers un moniteur Uptime Kuma de type *Push*. Ça détecte un process mort ou une boucle asyncio bloquée entre deux publications, qui peuvent être espacées de plusieurs heures.

Uptime Kuma est déployé sur ce serveur sous `/opt/docker/uptime-kuma` (même convention `compose.yml` que les autres stacks), accessible sur `http://<ip-serveur>:3001`. La création du compte admin est une étape web interactive obligatoire (pas d'automatisation possible sans définir un mot de passe à la place de l'utilisateur) : visiter l'URL une fois, créer le compte, ajouter un moniteur *Push*, puis coller l'URL générée dans `UPTIME_KUMA_PUSH_URL`.

## Logs

- Logs structurés sur stdout (`docker logs` / Portainer) **et** fichier tournant `logs/app.log` (5 Mo × 5).
- Le driver `json-file` de Docker est borné (`max-size: 10m`, `max-file: 5`) pour éviter une croissance illimitée.
- Les logs `httpx`/`httpcore` sont volontairement passés en `WARNING` : ces libs loguent l'URL complète des appels API, qui contient le token Telegram en clair.

## Sécurité

- Le conteneur tourne en **non-root** (utilisateur `franck`, UID/GID alignés sur l'hôte via `APP_UID`/`APP_GID`).
- Pas de socket Docker monté, pas de port exposé (aucune surface HTTP servie par ce projet).
- Le conteneur a accès en lecture/écriture à la **session Claude Code personnelle de l'hôte** (`~/.claude.json`, `~/.claude/`, `~/.local/*/claude`) — c'est ce qui permet d'utiliser l'abonnement Claude Code existant plutôt qu'une clé API séparée, mais ça élargit réellement la surface de confiance : ne pas faire `claude /logout` côté hôte pendant que le conteneur tourne, et garder les dépendances Python du projet à jour.
- Secrets uniquement dans `.env` (git-ignoré) ; `.env.example` documente les clés sans valeurs.

## Structure du dépôt

```
app/                  code applicatif (voir Architecture)
config/                prompts, thèmes de quiz, sources RSS — édité sans rebuild
scripts/                smoke tests, absents de l'image de production
data/                   app.db (SQLite), non versionné
logs/                   app.log, non versionné
backups/                sauvegardes SQLite, non versionné
Dockerfile
compose.yml
requirements.txt
.env / .env.example
```
