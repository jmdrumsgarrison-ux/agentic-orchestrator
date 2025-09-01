
import os, datetime, typing as t
import gradio as gr

APP_VERSION = "v0.8.5"
MODEL_NAME = os.environ.get("OPENAI_MODEL", "gpt-5")  # your space can override this
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY")

try:
    from openai import OpenAI
    _openai_available = True
except Exception:
    _openai_available = False

def _banner_md() -> str:
    return (
        f"### AO {APP_VERSION} — GPT: **{MODEL_NAME}** • Rich text input • Uploads\n"
        f"_Start typing on the left or compose rich text on the right and click **Use editor content**, then **Send**._"
    )

def _assistant_reply(messages: list[dict], files: list[str]|None) -> str:
    """
    Very small helper: if an API key and openai lib exist, call Chat Completions.
    Otherwise, return a local stub reply so the UI stays responsive.
    """
    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_text = m.get("content","")
            break

    # Attach a brief files note for the model (or stub) if any were uploaded.
    files_note = ""
    if files:
        files_note = f"\n\n(Attached files: {', '.join(os.path.basename(p) for p in files)})"

    if OPENAI_API_KEY and _openai_available:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages + [{"role":"system","content":"You are a helpful assistant in a Gradio Space."}],
                temperature=0.4,
            )
            return completion.choices[0].message.content or "OK."

        except Exception as e:
            return f"*(OpenAI call failed — returning local response. Error: {e})*\n\nYou said: {user_text}{files_note}"
    else:
        return f"*(Local response — no API call)*\n\nYou said: {user_text}{files_note}"

def respond(chat_history: list[dict], user_msg: str, uploads: list[gr.File]|None):
    # append user message to messages list used by Chatbot(type='messages')
    chat_history = chat_history or []
    chat_history.append({"role": "user", "content": user_msg})

    # collect filepaths
    filepaths = []
    if uploads:
        for f in uploads:
            # gradio passes temp file objects; we store paths only
            try:
                filepaths.append(getattr(f, "name", str(f)))
            except Exception:
                pass

    assistant = _assistant_reply(chat_history, filepaths)
    chat_history.append({"role": "assistant", "content": assistant})
    return chat_history, None, None  # clear text & uploads

with gr.Blocks(fill_height=True) as demo:
    gr.Markdown(_banner_md())

    with gr.Row(equal_height=True):
        with gr.Column(scale=3):
            chat = gr.Chatbot(type="messages", height=420, show_copy_button=True)
            user_tb = gr.Textbox(label="Textbox", placeholder="Type here…", scale=1)
        with gr.Column(scale=2):
            gr.Markdown("#### Rich text input (converted to Markdown on send)")
            rich = gr.RichText(placeholder="Write rich text here…", show_copy_button=True)
            use_btn = gr.Button("Use editor content", variant="secondary")
            uploads = gr.File(label="Upload files (optional)", file_count="multiple")
            send_btn = gr.Button("Send", variant="primary")

    # wire
    use_btn.click(lambda s: s, inputs=rich, outputs=user_tb)
    send_btn.click(
        respond,
        inputs=[chat, user_tb, uploads],
        outputs=[chat, user_tb, uploads],
    )
    user_tb.submit(
        respond,
        inputs=[chat, user_tb, uploads],
        outputs=[chat, user_tb, uploads],
    )

if __name__ == "__main__":
    demo.queue().launch()

