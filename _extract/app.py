import os, gradio as gr
from openai import OpenAI

VERSION = "AO v0.8.0 — GPT‑5 + uploads + banner"
PORT = int(os.environ.get("PORT","7860"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def make_messages(chat, user_text, files):
    messages = chat[:] if chat else []
    if user_text:
        content = user_text.strip()
    else:
        content = ""

    if files:
        # Just list filenames (avoid heavy file reads by default)
        names = [os.path.basename(f.name) for f in files]
        if content:
            content += "\n\n[Attached files: " + ", ".join(names) + "]"
        else:
            content = "[Attached files: " + ", ".join(names) + "]"
    if content:
        messages = messages + [{"role":"user","content":content}]
    return messages

def on_send(chat, text, files):
    text = (text or "").strip()
    # Build messages (append new user msg w/ file list if any)
    messages = make_messages(chat, text, files)

    if not text and not files:
        return chat, "", None  # nothing to do

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        reply = resp.choices[0].message.content
        chat = messages + [{"role":"assistant","content":reply}]
    except Exception as e:
        chat = messages + [{"role":"assistant","content":f"[error] {e}"}]

    # Reset text; keep files panel cleared after send
    return chat, "", None

with gr.Blocks(title=VERSION) as demo:
    gr.Markdown(f"### {VERSION}\nThis chat uses **{MODEL}** (override with `OPENAI_MODEL`).")
    chat = gr.Chatbot(type="messages", height=560)
    with gr.Row():
        msg = gr.Textbox(placeholder="Type here…", scale=7)
        send = gr.Button("Send", variant="primary", scale=1)
    uploads = gr.Files(label="Upload files (optional)", file_count="multiple")

    send.click(on_send, inputs=[chat, msg, uploads], outputs=[chat, msg, uploads])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
