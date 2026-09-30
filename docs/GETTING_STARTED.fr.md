# Premiers pas (sans aucune expérience en programmation)

🇬🇧 [English version](GETTING_STARTED.md)

Ce guide part du principe que tu n'as jamais ouvert un terminal de ta vie.
Il détaille chaque étape, dans l'ordre, avec le texte exact à taper.
Compte environ 15-20 minutes la première fois.

Si tu es déjà à l'aise avec la ligne de commande, le [README principal](../README.fr.md)
est plus rapide à suivre.

## Ce dont tu as besoin

- Un Mac (l'outil s'appuie sur Music.app, donc c'est macOS uniquement).
- Ton mot de passe administrateur (pour installer un seul logiciel).
- Un compte [iBroadcast](https://ibroadcast.com).
- Environ 15 minutes.

## Étape 1 — Ouvrir le Terminal

Le Terminal est une appli où tu tapes des commandes au lieu de cliquer. Ça
a l'air intimidant, mais tu vas seulement copier-coller quelques lignes.

1. Appuie sur `Cmd + Espace` pour ouvrir Spotlight.
2. Tape `Terminal`.
3. Appuie sur `Entrée`.

Une fenêtre avec du texte blanc ou noir devrait s'ouvrir. C'est le
Terminal — garde-le ouvert pour la suite de ce guide.

## Étape 2 — Installer Homebrew

Homebrew est la façon standard d'installer des outils de développement sur
un Mac. Si tu l'as déjà, cette étape ne fait rien de problématique — c'est
sans risque de la lancer quand même.

Copie cette ligne en entier, colle-la dans le Terminal (`Cmd + V`), puis
appuie sur `Entrée` :

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Ça va demander ton mot de passe Mac (tu ne verras pas les caractères en
tapant — c'est normal, tape-le simplement et appuie sur `Entrée`). Ça peut
prendre quelques minutes. Si ça affiche des instructions à la fin à propos
d'ajouter quelque chose à ton `PATH`, copie-colle et lance ces lignes
aussi — Homebrew te dit exactement quoi faire.

## Étape 3 — Installer Poetry

Poetry est l'outil que ce projet utilise pour se gérer lui-même. Colle
ceci et appuie sur `Entrée` :

```bash
brew install poetry
```

## Étape 4 — Télécharger le projet

1. Va sur la page GitHub du projet.
2. Clique sur le bouton vert **Code**, puis **Download ZIP**.
3. Trouve le fichier ZIP téléchargé (généralement dans ton dossier
   **Téléchargements**) et double-clique dessus pour le décompresser — ça
   crée un dossier nommé `ibroadcast-sync` (ou `ibroadcast-sync-main`).
4. Déplace ce dossier où tu veux le garder (par exemple ton dossier
   **Documents**).

## Étape 5 — Ouvrir le Terminal dans ce dossier

Retourne dans le Terminal, tape `cd` suivi d'une espace (n'appuie pas
encore sur Entrée), puis **glisse le dossier `ibroadcast-sync` depuis le
Finder directement dans la fenêtre du Terminal**. Le Finder remplira le
chemin complet pour toi. Appuie ensuite sur `Entrée`.

Ça devrait ressembler à quelque chose comme :

```text
cd /Users/tonnom/Documents/ibroadcast-sync
```

## Étape 6 — Installer le projet

Colle ceci et appuie sur `Entrée` :

```bash
poetry install
```

Ça télécharge tout ce dont le projet a besoin. Ça peut prendre une minute
ou deux la première fois. Si ça affiche une erreur à la place, regarde la
section [Dépannage](#dépannage) plus bas.

## Étape 7 — Récupérer tes identifiants iBroadcast

Le projet doit s'identifier auprès d'iBroadcast avant de pouvoir uploader
quoi que ce soit en ton nom. C'est une configuration à faire une seule
fois.

1. Va sur [ibroadcast.com](https://ibroadcast.com) et connecte-toi.
2. Fais défiler tout en bas de la page et clique sur **Developer**.
3. Clique pour créer une nouvelle app.
4. Dans le champ **Redirect URI**, entre exactement :

   ```text
   http://localhost:8912/callback
   ```

   (Copie-colle plutôt que de le taper — ça doit correspondre exactement.)
5. Enregistre, puis copie le **Client ID** fourni (une longue chaîne de
   lettres et de chiffres). Garde cette page ouverte, tu en auras besoin
   dans un instant.

## Étape 8 — Enregistrer ton Client ID

Retourne dans le Terminal, colle ceci et appuie sur `Entrée` :

```bash
cp .env.example .env
open -e .env
```

Une fenêtre d'éditeur de texte s'ouvre. Tu verras une ligne qui ressemble
à :

```text
IBROADCAST_CLIENT_ID=
```

Clique juste après le signe `=` et colle ton Client ID de l'étape 7, pour
que la ligne devienne quelque chose comme
`IBROADCAST_CLIENT_ID=abc123tonid`. Enregistre le fichier (`Cmd + S`) et
ferme la fenêtre de l'éditeur.

## Étape 9 — Lancer le script

Retourne dans le Terminal :

```bash
poetry run ibroadcast-sync
```

La première fois, il pose quelques questions en clair (uploader les
nouveaux morceaux ? synchroniser les playlists ? etc.) — répondre `y` pour
oui ou `n` pour non, ou simplement appuyer sur `Entrée` pour accepter la
suggestion entre crochets, convient très bien pour un premier essai.

Ton navigateur web va ensuite s'ouvrir, te demandant de te connecter à
iBroadcast et d'autoriser l'app — c'est normal, clique pour continuer.
Une fois fait, reviens au Terminal, la synchronisation démarre.

**Astuce pour le tout premier lancement :** à la question « Simulation
mode (dry-run) ? », réponds `y` (oui). Ça te montre ce qui *se passerait*
sans rien uploader ni modifier réellement — un moyen sûr de vérifier que
tout a l'air correct avant de le faire pour de vrai.

## Relancer plus tard

Chaque fois que tu veux synchroniser à nouveau, ouvre le Terminal, relance
la commande `cd` de l'étape 5 (ou glisse à nouveau le dossier), puis :

```bash
poetry run ibroadcast-sync
```

Pas besoin de refaire les étapes 2 à 8 — c'était une configuration à faire
une seule fois. Tu n'auras pas non plus besoin de te reconnecter à
iBroadcast dans le navigateur ; il se souvient de toi.

## Dépannage

**« command not found: brew » après l'étape 2** — ferme complètement la
fenêtre du Terminal, ouvre-en une nouvelle (étape 1 à nouveau), et
retente l'étape 3. Homebrew a parfois besoin d'une fenêtre de Terminal
toute fraîche pour être reconnu.

**`poetry install` affiche un mur de texte rouge** — copie les dernières
lignes de l'erreur et cherche-les, ou demande à quelqu'un ayant de
l'expérience en dev — la [section Dépannage complète du README principal](../README.fr.md#dépannage)
couvre la cause la plus fréquente (un conflit avec `pyenv`).

**Le navigateur ne s'ouvre pas à l'étape 9** — le Terminal affiche une
adresse web (qui commence par `https://`) juste avant de dire qu'il
attend. Copie cette adresse entière et colle-la manuellement dans ton
navigateur.

**Rien ne correspond / plein de messages « non trouvé »** — c'est normal
lors du tout premier lancement si tu n'as pas encore uploadé ta musique
sur iBroadcast. Lance-le pour de vrai (`poetry run ibroadcast-sync`,
réponds `n` au dry-run) une fois pour tout uploader, puis les playlists et
les notes devraient correspondre au lancement suivant.

## Automatiser (optionnel, plus avancé)

Une fois à l'aise avec le lancement manuel et que ça se comporte comme
prévu, il est possible de faire tourner la synchronisation automatiquement
chaque nuit sans rien faire. Cette partie implique d'éditer un fichier de
configuration à la main — voir
[`docs/com.example.ibroadcast-sync.plist.example`](com.example.ibroadcast-sync.plist.example)
et la section « Automatisation (launchd) » du [README principal](../README.fr.md).
Si ça semble trop compliqué, c'est tout à fait normal de simplement lancer
`poetry run ibroadcast-sync` à la main à chaque fois.
