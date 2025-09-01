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

# AO v0.3.0 — Docker

## What's new
- **Save Progress to Git can bootstrap an empty repo**:
  - Detects empty GitHub repo (no commits / no default branch).
  - Creates an **orphan `main` branch**, writes `ops/plan.md` + `ops/logbook.md`, and pushes the **first commit**.
  - If a branch exists, behavior is unchanged (diff preview, optional dry-run).

## Paths
- Read-only clone: `/tmp/repo_ro`
- Save-to-Git working clone: `/tmp/repo_rw`

## Secrets / env
- `GITHUB_TOKEN` — required for Save-to-Git (write permissions).
- `OPENAI_API_KEY` — for Ask ChatGPT (optional; API billing required).
- `ALLOWLIST_REPOS` — optional CSV of `owner/repo` allowed for writes.
