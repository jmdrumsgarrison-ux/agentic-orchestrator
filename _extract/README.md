# AO v0.8.2 — GPT‑5 chat + separate uploads (safe)

This drop restores a **plain, reliable chat loop** using your OpenAI key and keeps **uploads** on a *separate* flow so text
is never misrouted as a file (fixes the `InvalidPathError ... not uploaded by a user`).

## What’s included
- `app.py` — Gradio app
  - Clean `Chatbot` + `Textbox` for text
  - Separate `Files` + `Gallery` for uploads/preview
  - Version banner and model name
- `requirements.txt` — `gradio` + `openai`

## Configure
Set environment variables in your Space:
- `OPENAI_API_KEY` — required
- `OPENAI_MODEL` — optional, default `gpt-5`
- `SYSTEM_PROMPT` — optional

## Run locally
```bash
pip install -r requirements.txt
python app.py
```

## Notes
- We use Chat Completions for broad compatibility.
- Uploads are previewed only; parsing them is app‑specific and can be added without touching the chat handler.
