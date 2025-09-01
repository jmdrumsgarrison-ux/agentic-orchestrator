import os, shutil, gradio as gr

PORT = int(os.environ.get("PORT","7860"))
UP = "/tmp/ao_uploads"; os.makedirs(UP, exist_ok=True)

def init():
    chat = [{"role":"assistant","content":"New chat started. Paste any context you want and continue the conversation."}]
    gallery = []
    status = "Ready."
    return chat, gallery, status

def on_send(chat, text):
    text = (text or "").strip()
    if not text:
        return chat, ""
    chat = (chat or []) + [
        {"role":"user","content":text},
        {"role":"assistant","content":"(reply) Acknowledged. Share logs/screenshots if helpful; I can reason from there."},
    ]
    return chat, ""

def on_upload(files, chat, gallery):
    saved = []
    if files:
        for f in files:
            if not f: continue
            dst = os.path.join(UP, os.path.basename(f.name))
            shutil.copy2(f.name, dst)
            saved.append(dst)
    if saved:
        names = ", ".join(os.path.basename(s) for s in saved)
        chat = (chat or []) + [{"role":"assistant","content":f"Received file(s): {names}"}]
        gallery = (gallery or []) + saved
        status = f"Stored {len(saved)} file(s) in /tmp."
    else:
        status = "No files received."
    return chat, gallery, status

with gr.Blocks(title="AO v0.7.5 — Vanilla Chat") as demo:
    chat = gr.Chatbot(type="messages", height=560)
    with gr.Row():
        msg = gr.Textbox(placeholder="Type here…")
        send = gr.Button("Send", variant="primary")
    upload = gr.File(label="Upload files (optional)", file_count="multiple")
    gallery = gr.Gallery(label="Uploads", height=180)
    status = gr.Textbox(label="Upload status", interactive=False)

    demo.load(init, outputs=[chat, gallery, status])
    send.click(on_send, inputs=[chat, msg], outputs=[chat, msg])
    upload.upload(on_upload, inputs=[upload, chat, gallery], outputs=[chat, gallery, status])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
