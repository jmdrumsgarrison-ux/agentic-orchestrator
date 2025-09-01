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

# AO v0.5.2 — Docker (Focused + Context Bootstrap)

Scope (focused)
- **Only one capability:** Create a **Hugging Face Space** from a **GitHub repo**.

What's new
- Conversational **slot‑filling**: AO asks for missing info (repo URL, name, hardware).
- **Dry‑run first**, execute only on explicit “yes/proceed”.
- **Auto‑commit** a starter `ops/context.yaml` into your AO repo (if missing) so the banner is versioned.

Env / Secrets
- `GITHUB_TOKEN` — GitHub write access (required)
- `HF_TOKEN` — Hugging Face write for Spaces (required for creation)
- `AO_DEFAULT_REPO` — your AO server-of-record repo (required)
- `HF_NAMESPACE` — your HF org/user for new Spaces (recommended)
- `JOBS_MAX_PER_DAY` — cap on conversational jobs (default 3)
