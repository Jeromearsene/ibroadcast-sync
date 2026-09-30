# Getting started (no coding experience needed)

🇫🇷 [Version française](GETTING_STARTED.fr.md)

This guide assumes you've never opened a terminal before. It walks through
every single step, in order, with the exact text to type. It should take
about 15-20 minutes the first time.

If you're comfortable with the command line already, the main
[README](../README.md) is faster to follow instead.

## What you'll need

- A Mac (this tool relies on Music.app, so it's macOS-only).
- Your admin password (to install one piece of software).
- An [iBroadcast](https://ibroadcast.com) account.
- About 15 minutes.

## Step 1 — Open the Terminal

The Terminal is an app where you type commands instead of clicking. It
looks intimidating but you'll only ever copy-paste a handful of lines.

1. Press `Cmd + Space` to open Spotlight search.
2. Type `Terminal`.
3. Press `Enter`.

A window with white or black text should open. That's the Terminal — keep
it open for the rest of this guide.

## Step 2 — Install Homebrew

Homebrew is the standard way to install developer tools on a Mac. If you
already have it, this step does nothing harmful — it's safe to run either
way.

Copy this whole line, paste it into the Terminal (`Cmd + V`), then press
`Enter`:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It will ask for your Mac password (you won't see the characters as you
type — that's normal, just type it and press `Enter`). It may take a few
minutes. If it prints instructions at the end about adding something to
your `PATH`, copy-paste and run those lines too — Homebrew tells you
exactly what to run.

## Step 3 — Install Poetry

Poetry is the tool this project uses to manage itself. Paste this and
press `Enter`:

```bash
brew install poetry
```

## Step 4 — Download the project

1. Go to the project's GitHub page.
2. Click the green **Code** button, then **Download ZIP**.
3. Find the downloaded ZIP file (usually in your **Downloads** folder) and
   double-click it to unzip it — this creates a folder named
   `ibroadcast-sync` (or `ibroadcast-sync-main`).
4. Move that folder wherever you'd like to keep it (e.g. your **Documents**
   folder).

## Step 5 — Open the Terminal in that folder

Back in the Terminal, type `cd` followed by a single space (don't press
Enter yet), then **drag the `ibroadcast-sync` folder from Finder straight
into the Terminal window**. Finder will fill in the full path for you.
Then press `Enter`.

It should look something like:

```text
cd /Users/yourname/Documents/ibroadcast-sync
```

## Step 6 — Install the project

Paste this and press `Enter`:

```bash
poetry install
```

This downloads everything the project needs. It can take a minute or two
the first time. If it prints an error instead, see
[Troubleshooting](#troubleshooting) below.

## Step 7 — Get your iBroadcast credentials

The project needs to identify itself to iBroadcast before it can upload
anything on your behalf. This is a one-time setup.

1. Go to [ibroadcast.com](https://ibroadcast.com) and log in.
2. Scroll to the very bottom of the page and click **Developer**.
3. Click to create a new app.
4. In the **Redirect URI** field, enter exactly:

   ```text
   http://localhost:8912/callback
   ```

   (Copy-paste this rather than typing it — it must match exactly.)
5. Save, then copy the **Client ID** it gives you (a long string of
   letters and numbers). Keep this page open, you'll need it in a second.

## Step 8 — Save your Client ID

Back in the Terminal, paste this and press `Enter`:

```bash
cp .env.example .env
open -e .env
```

A text editor window opens. You'll see a line that looks like:

```text
IBROADCAST_CLIENT_ID=
```

Click right after the `=` sign and paste your Client ID from Step 7, so
the line reads something like `IBROADCAST_CLIENT_ID=abc123yourid`. Save
the file (`Cmd + S`) and close the editor window.

## Step 9 — Run it

Back in the Terminal:

```bash
poetry run ibroadcast-sync
```

The first time, it asks a few questions in plain English (upload new
songs? sync playlists? etc.) — answering with `y` for yes or `n` for no,
or just pressing `Enter` to accept the suggestion in brackets is fine for
a first run.

Your web browser will then open, asking you to log into iBroadcast and
authorize the app — this is expected, click through it. Once done, switch
back to the Terminal and the sync will start.

**Tip for the very first run:** when asked "Simulation mode
(dry-run)?", answer `y` (yes). This shows you what *would* happen without
actually uploading or changing anything — a safe way to check everything
looks right before doing it for real.

## Running it again later

Every time you want to sync again, open the Terminal, run the `cd`
command from Step 5 again (or just re-drag the folder in), then:

```bash
poetry run ibroadcast-sync
```

You won't need to repeat Steps 2-8 — those were one-time setup. You also
won't need to log into iBroadcast again in the browser; it remembers you.

## Troubleshooting

**"command not found: brew" after Step 2** — close the Terminal window
entirely, open a new one (Step 1 again), and retry Step 3. Homebrew
sometimes needs a fresh Terminal window to be recognized.

**`poetry install` prints a wall of red text** — copy the last few lines
of the error and search for them, or ask someone with dev experience —
the full [Troubleshooting section in the main README](../README.md#troubleshooting)
covers the most common cause (a `pyenv` conflict).

**The browser doesn't open in Step 9** — the Terminal prints a web
address (starting with `https://`) right before it says it's waiting.
Copy that whole address and paste it into your browser manually.

**Nothing seems to match / lots of "not found" messages** — this is
normal on the very first run if you haven't uploaded your music to
iBroadcast yet. Run it for real (`poetry run ibroadcast-sync`, answer `n`
to dry-run) once to upload everything, then playlists and ratings should
match up on the next run.

## Automating it (optional, more advanced)

Once you're comfortable running the sync manually and it behaves the way
you expect, it's possible to have your Mac run it automatically every
night without you doing anything. This part does involve editing a
configuration file by hand — see
[`docs/com.example.ibroadcast-sync.plist.example`](com.example.ibroadcast-sync.plist.example)
and the "Automation (launchd)" section of the [main README](../README.md).
If that feels like too much, it's completely fine to just run
`poetry run ibroadcast-sync` by hand whenever you want to sync.
