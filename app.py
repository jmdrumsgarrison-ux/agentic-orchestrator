import os, shutil, time, gradio as gr

PORT = int(os.environ.get("PORT","7860"))
UP = "/tmp/ao_uploads"; os.makedirs(UP, exist_ok=True)

SEED = """\
**Working agreement**
- You are the product owner/tester. You describe problems/features and share logs/screenshots.
- I am the developer/maintainer. I propose changes and deliver versioned zips (drops) on request.
- Loop: you ask → I propose/drop → you test → send logs → I patch → new drop. Repeat until stable.
- Packaging-first: you don’t hand-edit files; you swap in the zip I deliver.
- Style: concise. I keep notes short; I explain more only if you ask.
"""

def _init():
    chat = [
        {"role":"assistant","content":"AO is ready. This is a standard chat seeded with our working agreement. Tell me what you want to change or fix."}
    ]
    gallery = []
    status = "Ready."
    return chat, gallery, status

def reset():
    return _init()

def on_chat(chat, text):
    text = (text or "").strip()
    if not text:
        return chat, ""
    # append user then assistant
    chat = (chat or []) + [
        {"role":"user","content":text},
        {"role":"assistant","content":"Got it. If you have screenshots or logs, upload them here and I’ll use them to propose the next drop."}
    ]
    return chat, ""

def on_upload(files, chat, gallery):
    saved = []
    if files:
        for f in files:
            if not f: 
                continue
            dst = os.path.join(UP, os.path.basename(f.name))
            shutil.copy2(f.name, dst)
            saved.append(dst)
    if saved:
        names = ", ".join(os.path.basename(s) for s in saved)
        chat = (chat or []) + [{"role":"assistant","content":f"Received {len(saved)} file(s): {names}"}]
        gallery = (gallery or []) + saved
        status = f"Stored {len(saved)} file(s) in /tmp."
    else:
        status = "No files received."
    return chat, gallery, status

with gr.Blocks(title="AO v0.7.4r1 — Chat (seeded) + uploads") as demo:
    gr.Markdown(SEED)
    chat = gr.Chatbot(type="messages", height=560)
    with gr.Row():
        msg = gr.Textbox(placeholder="Type as usual…")
        send = gr.Button("Send", variant="primary")
    with gr.Row():
        upload = gr.File(label="Upload screenshots/logs (multiple)", file_count="multiple")
    gallery = gr.Gallery(label="Uploads (latest session)", height=180, show_label=True)
    status = gr.Textbox(label="Upload status", interactive=False)

    demo.load(reset, outputs=[chat, gallery, status])
    send.click(on_chat, inputs=[chat, msg], outputs=[chat, msg])
    upload.upload(on_upload, inputs=[upload, chat, gallery], outputs=[chat, gallery, status])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
