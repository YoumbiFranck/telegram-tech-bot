# Guide d'utilisation — telegram-tech-bot

Ce guide couvre l'usage courant du bot une fois déployé : vérifier qu'il tourne, changer le contenu, gérer les incidents. Pour l'architecture et le détail technique, voir [README.md](README.md).

Tout se passe dans `/opt/docker/telegram-tech-bot` sur le serveur (`ssh franck@192.168.178.37`).

## Sommaire

- [Vérifier que tout va bien](#vérifier-que-tout-va-bien)
- [Commandes du quotidien](#commandes-du-quotidien)
- [Personnaliser le contenu](#personnaliser-le-contenu)
- [Changer les horaires de publication](#changer-les-horaires-de-publication)
- [Sauvegardes et restauration](#sauvegardes-et-restauration)
- [Problèmes courants](#problèmes-courants)
- [Mettre à jour le bot](#mettre-à-jour-le-bot)
- [Statistiques rapides](#statistiques-rapides)

## Vérifier que tout va bien

Trois endroits à consulter, du plus rapide au plus détaillé :

1. **Uptime Kuma** — `http://192.168.178.37:3001`. Le moniteur `telegram-tech-bot` doit être **Up**, avec un ping toutes les 5 minutes. S'il passe **Down**, le conteneur est arrêté ou planté — voir [Problèmes courants](#problèmes-courants).
2. **Le canal Telegram lui-même** — un post vers 08:00, un digest actus vers 08:15, puis à partir de 12:30 une série de 10 quiz sur le thème unique tiré au sort ce jour-là (6 faciles, 2 intermédiaires, 2 difficiles), espacés de 8s — donc étalés sur 2-3 minutes. Les questions avec un extrait de code sont accompagnées d'une image.
3. **Les logs** :
   ```bash
   cd /opt/docker/telegram-tech-bot
   docker compose logs -f --tail 100
   ```
   Une ligne `X publié: ...` par étape réussie ; `X déjà publié aujourd'hui, on saute` si le job a déjà tourné ; toute ligne `ERROR` mérite un coup d'œil.

Si `TELEGRAM_ADMIN_CHAT_ID` ou `RESEND_API_KEY`/`ALERT_EMAIL_TO` sont configurés dans `.env`, tu reçois automatiquement une alerte (Telegram et/ou email) en cas d'échec de génération — pas besoin de surveiller activement.

## Commandes du quotidien

Toutes à lancer depuis `/opt/docker/telegram-tech-bot` :

```bash
# Voir si le conteneur tourne
docker compose ps

# Suivre les logs en direct
docker compose logs -f

# Redémarrer (ex: après une modification de .env)
docker compose restart

# Arrêter / relancer
docker compose stop
docker compose start
```

`restart: unless-stopped` signifie que le bot redémarre tout seul après un reboot du serveur — pas d'action nécessaire de ta part dans ce cas.

### Déclencher un job manuellement (sans attendre l'heure planifiée)

Utile pour tester après une modification. Le job tourne une seule fois puis le processus quitte (le scheduler du conteneur en production continue de tourner normalement à côté) :

```bash
docker compose run --rm telegram-tech-bot python -m app.main --run-now tech_post
docker compose run --rm telegram-tech-bot python -m app.main --run-now news
docker compose run --rm telegram-tech-bot python -m app.main --run-now quiz
docker compose run --rm telegram-tech-bot python -m app.main --run-now backup
```

Par défaut, l'idempotence normale s'applique : si le job est déjà passé aujourd'hui, il est simplement sauté (log `déjà publié aujourd'hui, on saute`). Pour forcer une vraie republication de test malgré tout, ajoute `--force` :

```bash
docker compose run --rm telegram-tech-bot python -m app.main --run-now quiz --force
```

`--force` republie réellement (nouveaux appels Claude, vrais messages sur le canal) — pour `quiz`, ça régénère un batch complet de 10 questions sur le thème déjà tiré aujourd'hui (pas de nouveau tirage de thème), en plus de celles déjà publiées ce jour-là.

## Personnaliser le contenu

Ces fichiers sont montés en volume : **les modifier suffit, pas besoin de rebuild ni de redémarrer** (ils sont relus à chaque exécution de job).

### Thèmes de quiz

`config/quiz_themes.yaml` :

```yaml
themes:
  - Java
  - Python
  - SQL
  - Symfony
  - JavaScript
  - TypeScript
  - PHP
  - Git
  - Linux
  - Docker
```

**Chaque jour, un seul thème de cette liste est tiré au sort** (les thèmes utilisés dans les 14 derniers jours sont évités tant qu'il en reste un non utilisé), et les 10 questions du jour portent toutes dessus. Ajouter/retirer un thème change juste le pool de tirage, pas le nombre de questions par jour (toujours 10, réparties 6 faciles / 2 intermédiaires / 2 difficiles).

Pour savoir quel thème a été tiré aujourd'hui :
```bash
docker compose run --rm telegram-tech-bot python -c "
from app.core.settings import load_settings
from app.persistence.db import connect
from app.persistence.repository import Repository
s = load_settings()
print(Repository(connect(s.data_dir / 'app.db')).get_quiz_theme_for_today())
"
```

### Sources d'actualités

`config/news_sources.yaml` :

```yaml
sources:
  - name: "Hacker News"
    url: "https://news.ycombinator.com/rss"
```

Ajoute une source en donnant un `name` et une `url` de flux RSS/Atom valide. Un flux cassé ou indisponible est simplement ignoré (loggé), il ne bloque pas les autres.

### Style des posts générés

`app/generation/prompts/*.md` — trois fichiers, un par type de contenu :
- `tech_post.md` — le post culture générale du matin
- `news_digest.md` — le digest d'actus
- `quiz.md` — la génération de quiz

Ce sont des instructions en langage naturel envoyées à Claude. Modifie le ton, la longueur, les contraintes directement dans ces fichiers. **Ces fichiers sont copiés dans l'image Docker** (contrairement aux deux ci-dessus) — après modification, il faut rebuild :

```bash
docker compose build && docker compose up -d
```

## Changer les horaires de publication

Dans `.env` :

```
SCHEDULE_TECH_POST_CRON=0 8 * * *
SCHEDULE_NEWS_CRON=15 8 * * *
SCHEDULE_QUIZ_CRON=30 12 * * *
SCHEDULE_BACKUP_CRON=0 3 * * *
```

Format cron standard (`minute heure jour mois jour_semaine`). Après modification :

```bash
docker compose restart
```

## Sauvegardes et restauration

Une sauvegarde de la base (`data/app.db`) est faite automatiquement chaque nuit à 03:00 dans `backups/app-YYYY-MM-DD.db`, avec 14 jours d'historique conservés.

**Restaurer une sauvegarde** (ex: après une corruption ou une suppression accidentelle) :

```bash
cd /opt/docker/telegram-tech-bot
docker compose stop
cp backups/app-2026-07-24.db data/app.db
docker compose start
```

Restaurer la base fait perdre l'historique de déduplication postérieur à la date de la sauvegarde — le bot pourrait republier un article ou une question déjà vue entre-temps. Sans gravité, juste un doublon occasionnel.

**Sauvegarde manuelle immédiate** (avant une manipulation risquée par exemple) :

```bash
docker compose run --rm telegram-tech-bot python -c "
from app.core.settings import load_settings
from app.persistence.backup import backup_database
s = load_settings()
backup_database(s.data_dir / 'app.db', s.backups_dir)
"
```

## Problèmes courants

**Le moniteur Uptime Kuma passe Down**
```bash
docker compose ps        # le conteneur est-il "Up" ?
docker compose logs --tail 50
docker compose up -d     # le relance s'il s'est arrêté
```

**Un job échoue avec "Not logged in" côté Claude**
La session Claude Code sur l'hôte a expiré ou a été déconnectée. Se reconnecter en SSH :
```bash
claude /login
```
Aucune action côté conteneur n'est nécessaire — la session est bind-montée, elle est reprise automatiquement au prochain job planifié.

**Rien ne se publie alors que l'heure est passée**
Vérifier que le job du jour n'a pas déjà tourné (idempotence) :
```bash
docker compose run --rm telegram-tech-bot python -c "
from app.core.settings import load_settings
from app.persistence.db import connect
from app.persistence.repository import Repository
import datetime
s = load_settings()
repo = Repository(connect(s.data_dir / 'app.db'))
print(repo.has_step_run(datetime.date.today().isoformat(), 'tech_post'))
"
```
`True` = déjà publié aujourd'hui, c'est normal qu'il ne se repasse rien. `False` avec l'heure passée → regarder les logs pour une erreur.

**Un quiz ou un post généré est de mauvaise qualité**
Ajuster le prompt correspondant dans `app/generation/prompts/`, puis rebuild (voir [Personnaliser le contenu](#personnaliser-le-contenu)).

**Les questions de quiz avec code n'affichent jamais d'image (toujours en texte)**
Le service de rendu (`CODE_IMAGE_API_URL` dans `.env`) est probablement indisponible — ce n'est pas bloquant (repli automatique en texte tronqué), mais à vérifier :
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST "$CODE_IMAGE_API_URL" \
  -H "Content-Type: application/json" -d '{"code":"const x = 1;","language":"javascript"}'
```
`HTTP 200` attendu. Voir aussi `generation_errors` (catégorie `ImageFallback`) pour la fréquence des échecs.

**Le bot n'a plus posté depuis plusieurs jours**
```bash
docker compose logs --tail 200 | grep -i error
```
Regarder aussi la table `generation_errors` :
```bash
docker compose run --rm telegram-tech-bot python -c "
from app.core.settings import load_settings
from app.persistence.db import connect
s = load_settings()
conn = connect(s.data_dir / 'app.db')
for row in conn.execute('SELECT * FROM generation_errors ORDER BY created_at DESC LIMIT 10'):
    print(dict(row))
"
```

## Mettre à jour le bot

```bash
cd /opt/docker/telegram-tech-bot
git pull
docker compose build --pull
docker compose up -d
```

Pas de mise à jour automatique : une modification de la logique de génération ne doit jamais arriver sans être relue.

## Statistiques rapides

Quelques requêtes utiles sur `data/app.db` :

```bash
cd /opt/docker/telegram-tech-bot

# Combien de contenus publiés par type, au total
docker compose run --rm telegram-tech-bot python -c "
from app.core.settings import load_settings
from app.persistence.db import connect
s = load_settings()
conn = connect(s.data_dir / 'app.db')
for row in conn.execute('SELECT content_type, COUNT(*) FROM published_items WHERE status=\"published\" GROUP BY content_type'):
    print(row)
"

# Répartition des quiz par thème, 30 derniers jours
docker compose run --rm telegram-tech-bot python -c "
from app.core.settings import load_settings
from app.persistence.db import connect
s = load_settings()
conn = connect(s.data_dir / 'app.db')
for row in conn.execute(\"SELECT theme, COUNT(*) FROM published_items WHERE content_type='quiz' AND published_at >= datetime('now','-30 days') GROUP BY theme\"):
    print(row)
"
```
