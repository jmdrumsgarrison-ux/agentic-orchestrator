
import os
import time
from typing import List, Tuple, Any
import gradio as gr
from markdownify import markdownify as html_to_md
from openai import OpenAI

APP_VERSION = "v0.8.3-fix-rte"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")

def _banner_dict() -> dict:
    return {
        "version": APP_VERSION,
        "model": DEFAULT_MODEL,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

def _chat_completion(messages: List[dict]) -> str:
    if not OPENAI_API_KEY:
        # No key in Spaces testing; return echo so UI still works
        last = next((m["content"] for m in reversed(messages) if m["role"]=="user"), "")
        return f"(demo mode) you said:\n\n{last}"
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content

def use_editor_content(html: str, chat: List[List[str]]) -> Tuple[List[List[str]], str]:
    """Called after the JS copies Quill HTML into this input."""
    md = html_to_md(html or "").strip()
    if not md:
        return chat, ""
    chat = chat + [[md, None]]
    # Build OpenAI messages
    msgs=[{"role":"system","content":"You are a helpful assistant."}]
    for u,a in chat:
        if u is not None:
            msgs.append({"role":"user","content":u})
        if a is not None:
            msgs.append({"role":"assistant","content":a})
    answer = _chat_completion(msgs)
    chat[-1][1] = answer
    return chat, ""

def send_text(text: str, chat: List[List[str]]) -> Tuple[List[List[str]], str]:
    if not text.strip():
        return chat, ""
    chat = chat + [[text, None]]
    msgs=[{"role":"system","content":"You are a helpful assistant."}]
    for u,a in chat:
        if u is not None:
            msgs.append({"role":"user","content":u})
        if a is not None:
            msgs.append({"role":"assistant","content":a})
    answer = _chat_completion(msgs)
    chat[-1][1] = answer
    return chat, ""

def add_upload(files: list, chat: List[List[str]]):
    """When files are uploaded, append a note describing them so the user can reference in text."""
    if not files:
        return gr.update()
    names = [getattr(f, "name", "file") for f in files]
    note = "Uploaded: " + ", ".join(names)
    # show note as a gray assistant line
    chat.append([None, f"📎 {note}"])
    return chat

def reset_chat():
    return []

css = """
#banner { font-size: 12px; opacity: .8; }
#rte_host .ql-container { min-height: 200px; }
#rte_host { position: relative; z-index: 2; }      /* ensure editor is on top */
#rte_host * { pointer-events: auto; }              /* allow typing/clicking */
"""

# Quill editor and toolbar; we mount it inside gr.HTML. We also create window.quill for JS access.
quill_html = """
<link href="https://cdn.jsdelivr.net/npm/quill@1.3.7/dist/quill.snow.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/quill@1.3.7/dist/quill.min.js"></script>
<div id="rte_host">
  <div id="toolbar">
    <span class="ql-formats">
      <button class="ql-bold"></button>
      <button class="ql-italic"></button>
      <button class="ql-underline"></button>
      <button class="ql-strike"></button>
    </span>
    <span class="ql-formats">
      <button class="ql-list" value="ordered"></button>
      <button class="ql-list" value="bullet"></button>
      <button class="ql-indent" value="-1"></button>
      <button class="ql-indent" value="+1"></button>
    </span>
    <span class="ql-formats">
      <select class="ql-header">
        <option selected></option>
        <option value="1"></option>
        <option value="2"></option>
        <option value="3"></option>
      </select>
    </span>
    <span class="ql-formats">
      <button class="ql-clean"></button>
    </span>
  </div>
  <div id="editor" style="height:220px;"></div>
</div>
<script>
  window.quill = new Quill('#editor', {
    theme: 'snow',
    readOnly: false,
    modules: { toolbar: '#toolbar' }
  });
</script>
"""

with gr.Blocks(css=css, fill_height=True) as demo:
    with gr.Row():
        gr.Markdown(f"**AO {APP_VERSION} — GPT:** `{DEFAULT_MODEL}` &nbsp;&nbsp;•&nbsp;&nbsp; **Uploads** &nbsp;&nbsp;•&nbsp;&nbsp; **Version banner**", elem_id="banner")
    with gr.Row():
        with gr.Column(scale=6):
            chat = gr.Chatbot(height=520, label="Chat")
        with gr.Column(scale=4):
            gr.Markdown("### Rich text input (Quill) → Markdown → chat")
            editor = gr.HTML(quill_html)
            html_buffer = gr.Textbox(visible=False)  # receive HTML via JS
            use_btn = gr.Button("Use editor content")
            # When clicked, we run a JS snippet that returns editor HTML; Gradio puts it into html_buffer
            use_btn.click(
                fn=None,
                inputs=None,
                outputs=html_buffer,
                js="() => (window.quill ? window.quill.root.innerHTML : '')"
            ).then(use_editor_content, inputs=[html_buffer, chat], outputs=[chat, html_buffer])
            gr.Markdown("or type plain text:")
            text = gr.Textbox(placeholder="Type here… (Shift+Enter for newline)", lines=4)
            send = gr.Button("Send")
            send.click(send_text, inputs=[text, chat], outputs=[chat, text])

    with gr.Row():
        uploads = gr.Files(label="Upload files (images, logs, etc.)", file_count="multiple", type="filepath")
        uploads.change(add_upload, inputs=[uploads, chat], outputs=chat)

    with gr.Row():
        gr.Button("Reset chat").click(fn=reset_chat, outputs=chat)

    demo.load(fn=lambda: _banner_dict(), outputs=None)

if __name__ == "__main__":
    demo.queue().launch()

