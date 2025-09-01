
import os
import base64
import gradio as gr

try:
    from markdownify import markdownify as mdify
except Exception:
    def mdify(html: str) -> str:
        import re
        return re.sub(r"<[^>]+>", "", html or "").strip()

USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")

def call_openai(messages):
    if not USE_OPENAI:
        raise RuntimeError("OPENAI_API_KEY not set")
    try:
        try:
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(model=OPENAI_MODEL, messages=messages)
            return resp.choices[0].message.content.strip()
        except Exception:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")
            resp = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=messages)
            return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(OpenAI error) {e}"

VERSION = "AO v0.8.9 — GPT‑5, rich editor, uploads, version banner"

QUILL_HTML = """
<link href="https://cdn.jsdelivr.net/npm/quill@1.3.7/dist/quill.snow.css" rel="stylesheet">
<div id="ql-container">
  <div id="editor" style="height:180px;"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/quill@1.3.7/dist/quill.min.js"></script>
<script>
  window.__ao_quill = new Quill('#editor', {
    theme: 'snow',
    modules: {
      toolbar: [
        ['bold', 'italic', 'underline'],
        [{'list': 'ordered'}, {'list': 'bullet'}],
        [{'header': [1, 2, 3, false]}],
        ['blockquote', 'code-block'],
        ['clean']
      ]
    }
  });
  window.__ao_get_html = function() {
    try { return window.__ao_quill.root.innerHTML; } catch(e) { return ''; }
  }
</script>
"""

def ensure_msg_html(html: str) -> str:
    if not html:
        return ""
    text = mdify(html)
    return text or ""

def step(messages, user_html, files):
    user_text = ensure_msg_html(user_html)
    attach_note = ""
    if files:
        names = [os.path.basename(getattr(f, 'name', str(f))) for f in files]
        attach_note = "\n\nAttachments: " + ", ".join(names)
    content = (user_text or "(no text)") + attach_note

    if messages is None:
        messages = []
    messages = list(messages)
    messages.append({"role": "user", "content": content})

    if USE_OPENAI:
        try:
            reply = call_openai(messages)
        except Exception as e:
            reply = f"(fallback) noted. Error calling OpenAI: {e}"
    else:
        reply = "I captured your message. (Set OPENAI_API_KEY to chat with GPT‑5.)"

    messages.append({"role": "assistant", "content": reply})
    return messages, gr.update(value="")

with gr.Blocks(fill_height=True, theme=gr.themes.Soft()) as demo:
    gr.Markdown(f"# {VERSION}")
    gr.Markdown("**Tip:** The editor on the right supports bold, italics, bullets, headers, quotes, and code. Your content is auto‑converted to Markdown.")

    with gr.Row():
        chat = gr.Chatbot(type="messages", height=420, label="Conversation")
        with gr.Column(scale=1, min_width=420):
            editor_html = gr.HTML(QUILL_HTML, elem_id="ao_quill")
            editor_buffer = gr.Textbox(visible=False)
            files = gr.File(label="Upload files (optional)", file_count="multiple")
            with gr.Row():
                send = gr.Button("Send", variant="primary")
                clear = gr.Button("Reset")

    send.click(
        fn=None,
        inputs=None,
        outputs=editor_buffer,
        js="window.__ao_get_html"
    ).then(
        fn=step,
        inputs=[chat, editor_buffer, files],
        outputs=[chat, editor_buffer]
    )

    def reset_all():
        return [], ""
    clear.click(fn=reset_all, inputs=None, outputs=[chat, editor_buffer])

if __name__ == "__main__":
    demo.launch()
