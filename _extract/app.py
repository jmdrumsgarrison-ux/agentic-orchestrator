
import os
import gradio as gr

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

APP_VERSION = "v0.8.6"
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()

BANNER = f"""
<div style="padding:10px 12px;
    background:linear-gradient(90deg,#4f46e5,#2563eb);
    color:#fff;border-radius:10px;margin-bottom:10px;font-weight:600">
  AO {APP_VERSION} — GPT-5 • Rich text • Uploads • Version banner
</div>
"""

def _make_client():
    if not OPENAI_KEY or OpenAI is None:
        return None
    try:
        return OpenAI()
    except Exception:
        return None

def _dry_run_reply(text):
    msg = text.strip() or "(empty message)"
    return f"(dry-run) No OPENAI_API_KEY set. I received: “{msg}”."

def send_fn(history, richtext, files):
    user_text = (richtext or "").strip()
    if not user_text:
        return history, gr.update(value="")
    new_messages = history + [{"role": "user", "content": user_text}]
    client = _make_client()
    if client is None:
        assistant_text = _dry_run_reply(user_text)
        new_messages.append({"role": "assistant", "content": assistant_text})
        return new_messages, gr.update(value="")
    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=new_messages,
            temperature=0.3,
        )
        assistant = resp.choices[0].message.content or ""
        new_messages.append({"role": "assistant", "content": assistant})
    except Exception as e:
        new_messages.append({"role": "assistant", "content": f"(error) {e}"})
    return new_messages, gr.update(value="")

with gr.Blocks(fill_height=True, theme=gr.themes.Soft()) as demo:
    gr.HTML(BANNER)
    with gr.Row():
        with gr.Column(scale=2):
            chat = gr.Chatbot(label="AO Chat", type="messages", height=520)
        with gr.Column(scale=1):
            gr.Markdown("**Rich text input**")
            editor = gr.RichText(
                placeholder="Write here… bullets, bold, links, etc.",
                show_copy_button=True,
            )
            send = gr.Button("Send", variant="primary")
            uploads = gr.File(file_count="multiple", label="Attach files")
            gr.Markdown(
                f"**Model:** `{MODEL_NAME}` | (Set OPENAI_MODEL / OPENAI_API_KEY)"
            )
    state = gr.State([])
    send.click(send_fn, inputs=[state, editor, uploads], outputs=[chat, editor])        .then(lambda h: h, inputs=chat, outputs=state)

if __name__ == "__main__":
    demo.queue().launch()
