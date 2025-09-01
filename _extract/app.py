import os, gradio as gr
from openai import OpenAI

PORT = int(os.environ.get("PORT","7860"))
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def on_send(chat, text):
    text = (text or "").strip()
    if not text:
        return chat, ""
    chat = (chat or []) + [{"role":"user","content":text}]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=chat,
        )
        reply = resp.choices[0].message.content
        chat.append({"role":"assistant","content":reply})
    except Exception as e:
        chat.append({"role":"assistant","content":f"[error] {e}"})
    return chat, ""

with gr.Blocks(title="AO v0.7.6 — Minimal Chat with OpenAI") as demo:
    chat = gr.Chatbot(type="messages", height=560)
    with gr.Row():
        msg = gr.Textbox(placeholder="Type here…", scale=9)
        send = gr.Button("Send", variant="primary", scale=1)
    send.click(on_send, inputs=[chat, msg], outputs=[chat, msg])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
