# Security

This is a personal utility, run locally, maintained by one person in
their spare time — there's no formal security process, but here's what's
relevant.

## What's sensitive

- **`data/ibroadcast_sync_token.json`** holds your iBroadcast OAuth
  access/refresh token. It's written with `chmod 600` (owner read/write
  only) and is excluded from git via `.gitignore`. If it leaks, revoke
  access from your iBroadcast account settings and delete the file - the
  next run will re-authenticate you.
- **`IBROADCAST_CLIENT_ID`** (your `.env`) identifies your personal
  iBroadcast developer app. Not as sensitive as the token (it can't act on
  its own, since this project uses Authorization Code + PKCE rather than a
  client secret), but still shouldn't be published — it's excluded from
  git the same way.
- **`data/ibroadcast_md5_cache.json`** and **`data/ibroadcast_library_dump.json`**
  contain your local file paths and library metadata (titles, artists,
  albums). Not credentials, but personal data about your music collection
  and folder structure - also git-ignored.

None of the above should ever end up in a commit. If you're about to push
for the first time, run `git status` and check nothing under `data/`
or `.env` is staged.

## Reporting an issue

If you find an actual vulnerability (not just a bug), please open a
[GitHub issue](https://github.com/Jeromearsene/ibroadcast-sync/issues) or
reach out to [Jeromearsene](https://github.com/Jeromearsene) directly
rather than posting exploit details publicly, if it's something that could
affect other users (e.g. a flaw in the OAuth flow itself, not just "my own
token leaked because I committed my data/ folder").

## Dependencies

[Dependabot](https://docs.github.com/en/code-security/dependabot) is
configured (`.github/dependabot.yml`) to open monthly PRs for outdated
Python dependencies and GitHub Actions versions.
