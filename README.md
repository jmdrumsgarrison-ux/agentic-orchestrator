---
title: Agentic Orchestrator (AO)
emoji: 🧠
colorFrom: green
colorTo: blue
sdk: docker
sdk_version: "1"
app_file: app.py
pinned: false
---

# AO v0.2.0 — Docker

What's new
- **Save Progress to Git** tab (safe write):
  - Writes an `ops/` bundle (`plan.md`, `logbook.md`).
  - **Diff preview** before committing.
  - **Dry Run** default ON (no push until you uncheck).
  - Optional branch selection (auto-detects if empty).
  - Uses `GITHUB_TOKEN` for authenticated pushes (required for private repos or when you cannot push anonymously).

Paths
- Read-only Git clones to: `/tmp/repo_ro`
- Save-to-Git clones to: `/tmp/repo_rw`

Env / Secrets
- `OPENAI_API_KEY` — for Ask ChatGPT (API billing must be enabled).
- `GITHUB_TOKEN` — for pushing commits in Save-to-Git.
- `ALLOWLIST_REPOS` (optional) — comma-separated list of `owner/repo` allowed to modify.
