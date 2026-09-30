# ibroadcast-sync

🇬🇧 [Read in English](README.md)

[![CI](https://github.com/Jeromearsene/ibroadcast-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/Jeromearsene/ibroadcast-sync/actions/workflows/ci.yml)

> Le badge pointe vers `Jeromearsene/ibroadcast-sync` — corrige l'URL ci-dessus si tu push sous un autre compte/nom de dépôt.

Synchronise ta bibliothèque musicale locale (via **Music.app** sur macOS, ou
un simple dossier) avec [iBroadcast](https://ibroadcast.com) :

1. **Upload** des nouveaux morceaux (dédup MD5 côté serveur, comme le script officiel iBroadcast).
2. **Playlists** : crée/met à jour les playlists iBroadcast à partir de celles de Music.app.
3. **Notes** (`--sync-ratings`) : convertit les étoiles Music.app (0-100) vers l'échelle iBroadcast (0-5).

Le tout pensé pour tourner sans surveillance (cron/launchd) une fois configuré.

> **Pas d'expérience avec la ligne de commande ?** Suis plutôt le
> [guide pas-à-pas pour débutant·e](docs/GETTING_STARTED.fr.md) — il ne
> suppose aucune connaissance préalable.

## Sommaire

- [Ce qui est vérifié vs. ce qui ne l'est pas](#ce-qui-est-vérifié-vs-ce-qui-ne-lest-pas)
- [Installation](#installation)
- [Configuration (créer ta propre app iBroadcast)](#configuration-créer-ta-propre-app-ibroadcast)
- [Premiers pas](#premiers-pas)
- [Usage](#usage)
- [Structure du projet](#structure-du-projet)
- [Développement : tests, typage, lint](#développement--tests-typage-lint)
- [Automatisation (launchd)](#automatisation-launchd)
- [Site web du projet](#site-web-du-projet)
- [Limites connues](#limites-connues)
- [Dépannage](#dépannage)

## Ce qui est vérifié vs. ce qui ne l'est pas

- **Le flow OAuth + upload** : repris quasi tel quel du script officiel
  [`iBroadcastMediaServices/ibroadcast-uploaders`](https://github.com/iBroadcastMediaServices/ibroadcast-uploaders)
  (MIT). Endpoints, format des requêtes, dédup MD5 : identiques à ce qui
  fonctionne déjà.
- **La lecture de la bibliothèque et les endpoints playlists**
  (`createplaylist`, `updateplaylist`) : basés sur la doc publique
  `help.ibroadcast.com/en/developer/api`. Le matching des morceaux
  (titre/artiste/album) part d'une hypothèse sur la structure JSON — **à
  vérifier avec `--dump-library` avant de faire confiance à la sync.**
- **L'extraction des playlists/notes Music.app** (JXA via `osascript`) :
  écrite à partir de la doc de scripting de Music.app. **À vérifier avec
  `--dump-playlists` en premier.**

Bref : la partie « upload » est du solide (reprise d'un script officiel
fonctionnel), la partie « playlists/notes » mérite une vérification chez toi
avant de l'automatiser sans surveillance.

## Installation

Prérequis : Python 3.9+, [Poetry](https://python-poetry.org/docs/#installation).

```bash
git clone <url-de-ton-repo>
cd ibroadcast-sync
poetry install
```

## Configuration (créer ta propre app iBroadcast)

Le client_id embarqué dans le script officiel n'a que les scopes
`account:read` + `upload` (insuffisant pour gérer les playlists), et surtout
il n'est habilité qu'au flow « device code » (le QR code). Les apps que tu
crées toi-même via « Developer » utilisent à la place le flow **Authorization
Code + PKCE** — c'est celui qu'utilise ce projet (navigateur + petit serveur
local temporaire pour capter la redirection, au lieu du QR code).

1. Va sur [ibroadcast.com](https://ibroadcast.com), connecte-toi, clique sur
   **Developer** en bas de la page de compte.
2. Crée une nouvelle app.
3. Renseigne un **Redirect URI**. Mets exactement :

   ```text
   http://localhost:8912/callback
   ```

   (ça doit correspondre caractère pour caractère à ce que le script envoie —
   schéma, port, chemin compris. Pour un autre port/chemin, voir
   `IBROADCAST_REDIRECT_URI` ci-dessous.)
4. Copie `.env.example` vers `.env` et renseigne le `client_id` obtenu :

   ```bash
   cp .env.example .env
   # puis édite .env
   ```

   `.env` est chargé automatiquement au prochain lancement du script —
   pas besoin de le sourcer ni d'exporter quoi que ce soit à la main.

## Premiers pas

### 1. Vérifier l'extraction des playlists (macOS, Music.app installé)

```bash
poetry run ibroadcast-sync --dump-playlists
```

Vérifie que tu récupères bien tes playlists avec titre/artiste/album pour
chaque morceau.

### 2. Première authentification + vérification de la bibliothèque

```bash
poetry run ibroadcast-sync --dump-library
```

La première fois, un onglet de navigateur s'ouvre automatiquement (sinon, le
lien est aussi affiché dans le terminal). Autorise l'app ; le script reprend
la main tout seul (il écoute brièvement sur `localhost:8912`). Le token est
mis en cache dans `data/ibroadcast_sync_token.json` (chmod 600) — plus besoin
de repasser par le navigateur pour les runs suivants, tant que le refresh
token reste valide.

Ça écrit la bibliothèque complète dans `data/ibroadcast_library_dump.json`.
Ouvre-le et vérifie la structure d'un morceau : champ `title`, et
`artist`/`album` en clair, ou plutôt `artist_id`/`album_id` pointant vers
`library['artists']` / `library['albums']` ? Le code gère les deux cas dans
`index_remote_tracks()` (`src/ibroadcast_sync/matching.py`), mais si les noms
de clés diffèrent de ce qui est supposé, c'est là qu'il faut ajuster.

### 3. Test à blanc

```bash
poetry run ibroadcast-sync --dry-run
```

Montre ce qui serait uploadé et quelles playlists seraient créées/mises à
jour, sans rien envoyer. Vérifie en particulier les morceaux listés comme
« non trouvés » pour une playlist — si tout le monde est non trouvé, le
matching titre/artiste/album ne fonctionne pas et il faut regarder le dump
de bibliothèque.

### 4. Pour de vrai

```bash
poetry run ibroadcast-sync
```

Sans aucun argument, un **assistant interactif** te guide (source des
fichiers, upload oui/non, playlists oui/non, dry-run, parallélisme). Dès
qu'un argument est présent, ce comportement est désactivé et les flags sont
pris tels quels (utile pour cron/launchd).

## Usage

```text
poetry run ibroadcast-sync [options]

--source-dir CHEMIN   Force un scan de ce dossier au lieu de demander les
                       emplacements à Music.app
--no-upload           Ne pas uploader de nouveaux fichiers
--no-playlists        Ne pas synchroniser les playlists
--workers N           Fichiers traités (hash + upload) en parallèle (défaut 4)
--dry-run             Simuler sans rien envoyer
--sync-ratings        Synchroniser les notes Music.app -> iBroadcast (0-5 étoiles)
--dump-library        Écrire la bibliothèque iBroadcast dans un JSON, puis quitter
--dump-playlists      Extraire les playlists Music.app, les afficher, puis quitter
```

Options utiles :

- `--no-playlists` : upload seul (pratique pour un cron nocturne fréquent).
- `--no-upload` : playlists seules.
- `--source-dir /autre/dossier` : par défaut, le script demande directement
  à Music.app l'emplacement de chaque piste (fonctionne quel que soit le
  disque — interne, externe, réseau).

Un launcher shell est aussi fourni pour éviter de retaper `poetry run` (et
donner à cron/launchd un chemin fixe à appeler, peu importe le dossier
courant) :

```bash
./scripts/run.sh --dry-run
```

## Structure du projet

```text
ibroadcast-sync/
├── pyproject.toml              # dépendances, script `ibroadcast-sync`, config Ruff/mypy/pytest (Poetry)
├── .env.example                # variables d'environnement à copier vers .env
├── .python-version             # version pyenv fixée pour que `poetry install` trouve un interpréteur qui marche
├── .markdownlint.json          # config lint markdown (utilisée par les éditeurs/CI qui vérifient la doc)
├── .pre-commit-config.yaml     # optionnel : lance Ruff automatiquement à chaque commit
├── .github/workflows/ci.yml    # lint + vérification de types + matrice de tests à chaque push/PR
├── .github/actions/setup-poetry/ # action composite partagée par les deux jobs CI
├── src/ibroadcast_sync/
│   ├── cli.py                  # argparse, assistant interactif, orchestration
│   ├── config.py               # constantes, URLs API, emplacement des données
│   ├── logging_utils.py        # log() horodaté, basé sur Rich
│   ├── oauth_client.py         # flow OAuth PKCE + client API iBroadcast
│   ├── md5_cache.py            # cache MD5 sur disque (chargement/sauvegarde/hash)
│   ├── progress.py             # barre de progression terminal live (upload + notes)
│   ├── upload.py               # découverte de fichiers + orchestration de l'upload parallèle
│   ├── musicapp.py             # pont JXA vers Music.app (pistes/playlists/notes)
│   ├── matching.py             # normalisation de texte + indexation de la bibliothèque distante
│   ├── playlists.py            # sync des playlists
│   └── ratings.py              # sync des notes
├── tests/                      # suite pytest (logique pure, appels réseau/macOS mockés)
├── data/                       # cache MD5, token OAuth, dumps, logs (ignoré par git)
├── scripts/run.sh              # launcher (se place à la racine du projet, puis `poetry run`)
└── docs/
    └── com.example.ibroadcast-sync.plist.example
```

**Le dossier `data/`** reste à la racine du projet plutôt que dans un dossier
caché du système (`~/.cache`, etc.) — exprès, pour rester facile à ouvrir et
inspecter (le cache MD5 en particulier). Il est exclu de git via
`.gitignore` (il contient un token OAuth et le détail de ta bibliothèque
locale). Son emplacement est configurable via `IBROADCAST_DATA_DIR` si tu
préfères autre chose.

## Développement : tests, typage, lint

```bash
poetry run pytest              # lance la suite de tests (avec résumé de couverture)
poetry run mypy src tests      # vérification de types (strict : disallow_untyped_defs)
poetry run ruff check .        # lint
poetry run ruff format .       # formatage
```

**Tests** (`tests/`, via [pytest](https://docs.pytest.org)) : couvrent la
logique pure — normalisation de texte et matching de bibliothèque, sync
des playlists, conversion des notes, cache MD5, découverte de fichiers,
génération PKCE, et rafraîchissement de token (mockés, aucun appel réseau
réel) — plus quelques vérifications structurelles sur `docs/index.html`
lui-même (équilibre des balises, pas d'id dupliqué, et que chaque bloc de
contenu anglais a bien son équivalent français). Volontairement non
couverts : les vrais appels HTTP et le pont macOS/JXA vers Music.app — les
mocker en profondeur coûterait plus cher que ce que ça détecterait de
bugs, pour un utilitaire personnel. La couverture tourne autour de 45-50% ;
c'est un compromis assumé, pas un trou à combler pour la forme.

**Typage** : tout le code est annoté et vérifié avec
[mypy](https://mypy.readthedocs.io) en mode quasi-strict
(`disallow_untyped_defs = true` — voir `[tool.mypy]` dans `pyproject.toml`).

**Lint/formatage** : [Ruff](https://docs.astral.sh/ruff/) gère les deux,
avec pycodestyle, pyflakes, isort, bugbear, pyupgrade, simplify,
comprehensions et pep8-naming actifs (voir `[tool.ruff]` /
`[tool.ruff.lint]`).

Tu peux aussi installer [pre-commit](https://pre-commit.com) pour lancer
Ruff automatiquement avant chaque commit :

```bash
pip install pre-commit
pre-commit install
```

Un workflow GitHub Actions (`.github/workflows/ci.yml`) lance ruff, mypy,
et la suite de tests (sur Python 3.9 et 3.12) à chaque push et pull
request.

## Automatisation (launchd)

Une fois que `--dry-run` te convainc que ça matche correctement, tu peux
planifier l'upload seul chaque nuit, et la sync des playlists moins souvent
(elle fait un fetch complet de la bibliothèque, donc un peu plus lourde).

Un exemple prêt à l'emploi est fourni dans
[`docs/com.example.ibroadcast-sync.plist.example`](docs/com.example.ibroadcast-sync.plist.example).
Adapte les chemins et ton `client_id`, copie-le vers
`~/Library/LaunchAgents/`, puis :

```bash
launchctl load ~/Library/LaunchAgents/com.example.ibroadcast-sync.plist
```

L'authentification n'est interactive qu'au tout premier run (celui que tu
lances toi-même dans un terminal, pas via launchd). Une fois le token en
cache dans `data/`, le job planifié tourne sans intervention — il se
rafraîchit tout seul via le refresh token, sans repasser par le navigateur.

## Site web du projet

Une petite page de présentation vit dans [`docs/index.html`](docs/index.html)
— pratique pour orienter quelqu'un plutôt que vers le README brut. Pour la
publier gratuitement via GitHub Pages : **Settings → Pages → Build and
deployment → Deploy from a branch** sur le dépôt, choisis la branche
`main` et le dossier **/docs**, enregistre. Elle sera en ligne sur
`https://<ton-pseudo>.github.io/ibroadcast-sync/` en une à deux minutes.

Les balises Open Graph / Twitter Card de la page (pour les aperçus de
lien sur Slack, Discord, etc.) contiennent cette même URL en dur dans
`og:url` — mets-la à jour dans `docs/index.html` si ton pseudo ou le nom
du dépôt diffère de `Jeromearsene/ibroadcast-sync`.

## Limites connues

- Le matching playlist/notes est exact (titre/artiste/album normalisés,
  insensible à la casse et aux accents), avec deux replis non-ambigus
  (titre+album, titre+artiste) — un featuring écrit très différemment entre
  Music.app et iBroadcast (ex. « feat. » vs « ft. ») peut malgré tout ne pas
  matcher. À surveiller sur les premiers runs (voir les logs « non
  trouvé(s) »).
- La normalisation de texte retire les accents/diacritiques via NFKD
  Unicode, ce qui fonctionne bien pour les titres en écriture latine mais
  peut réduire un titre en écriture non-latine (japonais, cyrillique...) à
  une chaîne quasi vide. Ça ne cause pas de mauvais matching (le triplet
  titre+artiste+album complet reste utilisé), mais ça peut rendre l'indice
  de diagnostic « morceau similaire » en mode verbeux bruyant pour les
  bibliothèques avec beaucoup de titres en écriture non-latine.
- `updateplaylist` remplace le contenu complet de la playlist à chaque run —
  si tu modifies une playlist directement sur iBroadcast entre deux syncs,
  ces changements seront écrasés par la version locale au prochain run.
- La conversion de note Music.app (0-100, demi-étoiles) vers l'échelle
  iBroadcast (entier 0-5) perd la demi-étoile (arrondie au point entier le
  plus proche).
- `--sync-ratings` attend au moins ~0,3s avant chaque appel API, même le
  tout premier (et davantage si le serveur limite le débit) — une
  précaution calibrée empiriquement contre le rate-limiter d'iBroadcast,
  pas un bug, mais ça signifie que noter une bibliothèque de plusieurs
  milliers de morceaux pour la première fois peut prendre un moment
  (quelques milliers de morceaux : environ 15-20 minutes au minimum).
- `get_music_app_playlists()` n'a pas de repli en boucle par morceau
  contrairement aux emplacements de fichiers et aux notes (voir
  `musicapp.py`) — si l'accès par lot JXA échoue franchement plutôt que de
  se dégrader champ par champ, la sync des playlists échoue pour tout le
  run au lieu de basculer sur une méthode plus lente.

## Dépannage

**`poetry install` / `poetry run` échoue avec `Command [...python...]
returned non-zero exit status 127` et/ou un message du genre « Python
poetry project detected. Run mkvenv to setup autoswitching »**

Ça n'a rien à voir avec ce projet — `pyproject.toml` ne demande que Python
3.9+, rien d'inhabituel. Ça vient d'une config `pyenv` problématique sur ta
machine, et le message « mkvenv » vient d'un plugin de prompt shell (dans
tes dotfiles) qui réagit à la présence d'un `pyproject.toml` — ce n'est pas
Poetry lui-même qui l'affiche.

Cause la plus fréquente : ta version **globale** pyenv est réglée sur
`system`, et sous macOS le Python système ne fournit qu'un binaire
`python3` — pas de `python` tout court. Le shim `pyenv/shims/python` n'a
donc rien à exécuter et échoue avec le code 127. Diagnostic :

```bash
pyenv versions   # ce qui est réellement installé (repère le `*`)
pyenv version    # ce que pyenv résout *ici*, et pourquoi
```

Si `pyenv version` affiche `system`, ou une version absente de
`pyenv versions`, ça confirme le diagnostic. Corrige-le pour ce projet
uniquement (sans toucher ton réglage global) — ce dépôt fournit déjà un
fichier `.python-version`, mais si tu veux choisir une autre version
installée :

```bash
pyenv local 3.10.8   # n'importe quelle version 3.9+ listée par `pyenv versions`
poetry install
```

Ou contourne pyenv entièrement et pointe Poetry vers ton Python système :

```bash
poetry env use $(which python3)
poetry install
```

## Licence

MIT — voir [`LICENSE`](LICENSE) (inclut l'attribution du code d'upload
repris du script officiel iBroadcast).
