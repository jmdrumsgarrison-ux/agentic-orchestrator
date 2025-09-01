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

# AO v0.5.1 — Docker (Conversational Context Packs)

New
- **Context Packs** for the conversational Jobs tab:
  - AO shows a dynamic **capabilities banner** the moment you open Jobs.
  - It loads a customizable file from your **AO_DEFAULT_REPO** (`ops/context.yaml`) if present.
  - If missing, AO falls back to a **built-in default**.
- **Examples drawer** with copy‑to‑chat snippets based on your enabled secrets.

Files added
- None in the Space repo (all in app). Optional: create `ops/context.yaml` in your AO repo to override the banner.

Optional `ops/context.yaml` (in AO_DEFAULT_REPO):
```yaml
intro: |
  I can create worker repos, seed from GitHub, and create HF Spaces. I always dry-run first.
capabilities:
  - Create GitHub repo (private) under your org
  - Seed from a public GitHub repo URL
  - Create a Hugging Face Space from that repo (Docker SDK)
  - Open PR-based change requests (coming soon)
guardrails:
  - Dry run by default, explicit yes to execute
  - Daily job cap and HF namespace scoping
examples:
  - "clone https://github.com/gaomingqi/Track-Anything into a new HF Space called aow-track-anything on cpu"
  - "create a worker repo called aow-reranker"
  - "modify the app to expose more controls"  # (will scaffold CR)
```
