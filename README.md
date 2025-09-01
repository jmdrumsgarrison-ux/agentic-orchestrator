---
title: AgentiveOrchestrator
emoji: 🧩
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "4.44.1"
app_file: app.py
pinned: false
---

# AO v0.8.7

Rich text editor (HTML under the hood, converted to Markdown) + file uploads + version banner.

- Uses Gradio Blocks.
- No dependency on gr.RichText (works across Gradio 4.x).
- Default model name shown from `OPENAI_MODEL` (defaults to "gpt-5").
