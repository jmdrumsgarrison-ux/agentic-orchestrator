---
title: AO v0.8.3 — GPT‑5 + uploads + rich text
emoji: 🧩
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "4.44.0"
app_file: app.py
pinned: false
---

This Space provides a **rich text chat** with:
- GPT model selectable via `OPENAI_MODEL` (defaults to `gpt-5`).
- File uploads (multiple).
- Quill-based editor (bullets, bold, headings) converted to **Markdown** before sending.
- Version banner at the top.

### Environment
Set your OpenAI key in Space **Secrets** as `OPENAI_API_KEY` (or `OPENAI_KEY`). Optionally set `OPENAI_MODEL`.
