import os
import time
from typing import List, Dict, Any, Tuple

import gradio as gr

# Optional OpenAI usage; falls back to echo if key not present
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY") or os.environ.get("OPENAI_APIKEY") or os.environ.get("OPENAI_KEY")

try:
    from openai import OpenAI  # >=1.0
    _openai_ok = True
except Exception:
    _openai_ok = False

BANNER = f"AO v0.8.3 — GPT: **{OPENAI_MODEL}** · Rich text input (Quill) → Markdown · File uploads · Version banner"

def _call_openai(messages: List[Dict[str, str]]) -> str:
    # If no key or SDK unavailable, gracefully echo a stub
    if not OPENAI_API_KEY or not _openai_ok:
        # Simple deterministic stub for offline demo
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"_demo reply:_ I received your message (as Markdown):\n\n{last_user}"
    client = OpenAI(api_key=OPENAI_API_KEY)
    # Use Responses API (chat) if available in your environment
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"OpenAI error: {e}"

def start_state() -> Tuple[List[Tuple[str, str]], List[Dict[str, str]]]:
    history = []
    sys_prompt = (
        "You are AO, an agentic orchestrator assistant. "
        "You can read Markdown bullets, code blocks, and images referenced by the user. "
        "Keep responses concise unless asked for detail."
    )
    messages = [{"role": "system", "content": sys_prompt}]
    return history, messages

def send(md_text: str, files: List[Any], history: List[Tuple[str, str]], messages: List[Dict[str, str]]):
    user_content = md_text or ""
    if files:
        # Show file names inline; in a more advanced app, you could parse images, etc.
        names = [os.path.basename(f.name) for f in files]
        user_content += "\n\n**Attached files:** " + ", ".join(names)
    messages = messages + [{"role": "user", "content": user_content}]
    assistant = _call_openai(messages)
    history = history + [(user_content, assistant)]
    messages = messages + [{"role": "assistant", "content": assistant}]
    return history, messages, gr.update(value="")

with gr.Blocks(css="""
#banner {padding:10px 12px; background: rgba(0,0,0,0.02); border-radius: 10px; border:1px solid #e5e7eb;}
.quill-wrap {border:1px solid #e5e7eb; border-radius:10px; overflow:hidden;}
#editor {min-height: 160px; background:white;}
#toolbar {border-bottom:1px solid #e5e7eb;}
""") as demo:
    gr.HTML(f"<div id='banner'><strong>{BANNER}</strong></div>")

    with gr.Row():
        with gr.Column(scale=3):
            chat = gr.Chatbot(label="Chat", type="messages", height=520, avatar_images=(None, None))
            files = gr.Files(label="Upload files (optional)", file_count="multiple", height=120)
        with gr.Column(scale=2):
            gr.Markdown("#### Rich text input\nUse toolbar for **bold**, *italics*, lists, etc. Content is converted to **Markdown** before sending.")
            md_hidden = gr.Textbox(value="", visible=False)  # receives Markdown via JS
            # Quill + Turndown in HTML panel
            gr.HTML("""
<link href="https://cdn.jsdelivr.net/npm/quill@1.3.7/dist/quill.snow.css" rel="stylesheet">
<div class="quill-wrap">
  <div id="toolbar">
    <span class="ql-formats">
      <select class="ql-header">
        <option selected></option>
        <option value="1"></option>
        <option value="2"></option>
      </select>
      <button class="ql-bold"></button>
      <button class="ql-italic"></button>
      <button class="ql-underline"></button>
    </span>
    <span class="ql-formats">
      <button class="ql-list" value="ordered"></button>
      <button class="ql-list" value="bullet"></button>
      <button class="ql-blockquote"></button>
      <button class="ql-link"></button>
    </span>
    <span class="ql-formats">
      <button class="ql-clean"></button>
    </span>
  </div>
  <div id="editor"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/quill@1.3.7/dist/quill.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/turndown@7.1.2/dist/turndown.js"></script>
<script>
  window._quill = new Quill('#editor', {
    theme: 'snow',
    placeholder: 'Type here… use the toolbar for bullets, headings, links…',
    modules: { toolbar: '#toolbar' }
  });
  window._turndown = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' });
</script>
            """)
            to_markdown = gr.Button("Use editor content")
            send_btn = gr.Button("Send", variant="primary")
            gr.Markdown("Tip: Click **Use editor content** to capture current rich text → Markdown, then **Send**.")

    history_state = gr.State([])       # Chat display tuples
    messages_state = gr.State([])      # OpenAI message list

    # Initialize states
    init = gr.Button("Reset chat")
    init.click(start_state, None, [chat, messages_state])

    # Capture rich text -> Markdown into hidden box
    to_markdown.click(
        None,
        js="""() => {
          const quill = window._quill;
          const html = quill ? quill.root.innerHTML : '';
          const md = window._turndown ? window._turndown.turndown(html) : html;
          return md;
        }""",
        outputs=md_hidden
    )

    # When sending, consume md_hidden
    send_btn.click(
        send,
        inputs=[md_hidden, files, chat, messages_state],
        outputs=[chat, messages_state, md_hidden]
    )

    # On load, bootstrap states
    demo.load(start_state, None, [chat, messages_state])

if __name__ == "__main__":
    demo.queue().launch()

