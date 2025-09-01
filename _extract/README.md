---
title: AgentiveOrchestrator
emoji: 🧩
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "4.44.1"
app_file: app.py
pinned: false
---

AO v0.8.5 — Gradio chat with rich text, uploads, and a version banner.

- Uses **Gradio 4.44.1** (pinned in `requirements.txt`).
- Reads model name from `OPENAI_MODEL` (default `"gpt-5"`).
- Optionally calls OpenAI if `OPENAI_API_KEY` is present.
