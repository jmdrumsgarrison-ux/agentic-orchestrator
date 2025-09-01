import os, io, base64, mimetypes
import gradio as gr
from openai import OpenAI

VERSION = "AO v0.8.1 — GPT‑5 (text) + vision uploads + banner"
PORT = int(os.environ.get("PORT","7860"))
TEXT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

MAX_TEXT_BYTES = 200_000  # read up to 200KB from text-like files

def to_data_url(path):
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "application/octet-stream"
    with open(path, "rb") as f:
        b = f.read()
    b64 = base64.b64encode(b).decode("ascii")
    return f"data:{mime};base64,{b64}", mime

def files_to_content(files, text):
    """
    Build OpenAI 'content' blocks for a user message.
    Includes text plus any image attachments via data URLs and
    short snippets of text files. Other files included by name only.
    """
    blocks = []
    txt = (text or "").strip()
    if txt:
        blocks.append({"type":"text","text": txt})

    for f in (files or []):
        path = f.name if hasattr(f, "name") else str(f)
        mime, _ = mimetypes.guess_type(path)
        if mime and mime.startswith("image/"):
            data_url, _ = to_data_url(path)
            blocks.append({"type":"image_url","image_url":{"url": data_url}})
        else:
            try:
                # Try to read limited bytes, assume text
                with open(path, "rb") as fh:
                    chunk = fh.read(MAX_TEXT_BYTES)
                snippet = None
                try:
                    snippet = chunk.decode("utf-8", errors="replace")
                except Exception:
                    snippet = None
                if snippet:
                    blocks.append({"type":"text","text": f"[Attached file: {os.path.basename(path)}]\n\n{snippet}"})
                else:
                    blocks.append({"type":"text","text": f"[Attached file: {os.path.basename(path)} (binary/not previewed)]"})
            except Exception:
                blocks.append({"type":"text","text": f"[Attached file: {os.path.basename(path)} (unreadable)]"})
    return blocks

def on_send(chat, text, files):
    # Build user content with any attachments
    content_blocks = files_to_content(files, text)
    if not content_blocks:
        return chat, "", None, []

    # Choose model: if any image blocks present, use vision model
    use_model = TEXT_MODEL
    if any(block.get("type") == "image_url" for block in content_blocks):
        use_model = VISION_MODEL

    try:
        resp = client.chat.completions.create(
            model=use_model,
            messages=[
                {"role":"system","content":"You are a helpful assistant embedded in a developer tool. Be concise and actionable."},
                * (chat if chat else []),
                {"role":"user","content": content_blocks},
            ],
        )
        reply = resp.choices[0].message.content
        new_chat = (chat or []) + [{"role":"user","content": content_blocks}, {"role":"assistant","content": reply}]
    except Exception as e:
        new_chat = (chat or []) + [{"role":"user","content": content_blocks}, {"role":"assistant","content": f"[error] {e}"}]

    # For preview area: show thumbnails for images
    thumbs = []
    for f in (files or []):
        path = f.name if hasattr(f, "name") else str(f)
        mime, _ = mimetypes.guess_type(path)
        if mime and mime.startswith("image/"):
            thumbs.append(path)

    return new_chat, "", None, thumbs

with gr.Blocks(title=VERSION) as demo:
    gr.Markdown(f"### {VERSION}\nText model: **{TEXT_MODEL}**, Vision model: **{VISION_MODEL}**.")
    chat = gr.Chatbot(type="messages", height=520)
    gallery = gr.Gallery(label="Image previews (this turn)", columns=6, height=140)
    with gr.Row():
        msg = gr.Textbox(placeholder="Type here…", scale=7)
        send = gr.Button("Send", variant="primary", scale=1)
    uploads = gr.Files(label="Upload files (optional)", file_count="multiple")

    send.click(on_send, inputs=[chat, msg, uploads], outputs=[chat, msg, uploads, gallery])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
