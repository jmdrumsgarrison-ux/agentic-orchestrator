import gradio as gr

PORT = int(os.environ.get("PORT","7860"))

def on_send(chat, text):
    text = (text or "").strip()
    if not text:
        return chat, ""
    chat = (chat or []) + [{"role":"user","content":text}]
    return chat, ""

with gr.Blocks(title="AO v0.7.5r2 — Minimal Chat") as demo:
    chat = gr.Chatbot(type="messages", height=560)
    with gr.Row():
        msg = gr.Textbox(placeholder="Type here…", scale=9)
        send = gr.Button("Send", variant="primary", scale=1)
    send.click(on_send, inputs=[chat, msg], outputs=[chat, msg])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
