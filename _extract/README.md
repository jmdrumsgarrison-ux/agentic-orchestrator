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

# AO v0.3.1 — Docker (Opinionated)

What changed
- **Repo URL optional**. Discovery order:
  1) `AO_DEFAULT_REPO` env (full https URL)
  2) Single item in `ALLOWLIST_REPOS` (owner/repo)
  3) Last used repo cache (`/tmp/ao_last_repo.json`)
- **Branch auto**: resolve remote default (`origin/HEAD`); fallback to `main`/`master`; create `main` for empty repos.
- **Auto plan/log**: AO generates `ops/plan.md` & `ops/logbook.md` content with version, goals, guardrails.
- **Auto-commit heuristic** (you don't decide):
  - If changes are only under `ops/`, diff < 100KB, and plan length >= 50 chars → commit & push.
  - Else → Dry Run with diff preview and a message asking for approval.
- **Output links** to the pushed files on GitHub.

Env / secrets
- `GITHUB_TOKEN` (write)
- `OPENAI_API_KEY` (optional)
- `ALLOWLIST_REPOS` (optional CSV of owner/repo)
- `AO_DEFAULT_REPO` (optional full https repo URL)
- `AO_AUTO_COMMIT` (optional; default: true)
