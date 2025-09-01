import os, io, shutil, zipfile, time, yaml, gradio as gr
from typing import List, Dict, Any

PORT = int(os.environ.get("PORT","7860"))
HOME = "/tmp/ao_home"; os.makedirs(HOME, exist_ok=True)

BANNER = """\
# AO v0.7.0 — Drops mode

This server mirrors our old working style:
- Open chat (broad, unstructured).
- Propose a **Drop** when ready (versioned bundle with notes).
- Upload files (patches, configs, screenshots) and include them in the Drop.
- Generate a **single downloadable zip** you can drag into a Space.

Nothing runs automatically; this is an authoring surface.
"""

def _ts(): return time.strftime("%Y-%m-%d %H:%M:%S")

def new_session():
    state = {
        "chat": [("system", "Welcome to AO v0.7.0 — Drops mode. Tell me what you want; I can help you craft a Drop.")],
        "draft": {
            "version": "v0.0.1",
            "title": "",
            "summary": "",
            "notes": [],
            "files": [],   # list of {"name":..,"path":..,"size":..}
        },
    }
    return state

def chat_step(history, user_text, state):
    state = state or new_session()
    history = history or []
    txt = (user_text or "").strip()
    if not txt: return history, "", state
    state["draft"]["notes"].append({"time":_ts(),"text":txt})
    # Lightweight reflection; keep it natural
    reply = "Got it. Let's shape this into a Drop. When you're ready, give me a **title** and a one‑paragraph **summary**, or upload files you want included."
    history = history + [(user_text, reply)]
    return history, "", state

def receive_files(files, state):
    state = state or new_session()
    added = []
    if files:
        for f in files:
            if not f: continue
            # Gradio supplies temp paths; copy into session dir
            updir = os.path.join(HOME, "uploads"); os.makedirs(updir, exist_ok=True)
            dst = os.path.join(updir, os.path.basename(f.name))
            shutil.copy2(f.name, dst)
            info = {"name": os.path.basename(dst), "path": dst, "size": os.path.getsize(dst)}
            state["draft"]["files"].append(info)
            added.append(info["name"])
    msg = "Attached: " + (", ".join(added) if added else "(none)")
    return gr.update(value=msg), state

def update_meta(version, title, summary, state):
    state = state or new_session()
    if version: state["draft"]["version"] = version.strip()
    if title is not None: state["draft"]["title"] = title.strip()
    if summary is not None: state["draft"]["summary"] = summary.strip()
    return state

def build_zip(state):
    state = state or new_session()
    d = state["draft"]
    if not d["title"]:
        return None, "Please provide a Drop title before building."
    # create bundle folder
    outroot = os.path.join(HOME, "bundle"); shutil.rmtree(outroot, ignore_errors=True); os.makedirs(outroot, exist_ok=True)
    # write summary docs
    with open(os.path.join(outroot, "DROP_NOTES.md"), "w", encoding="utf-8") as f:
        f.write(f"# {d['title']} ({d['version']})\n\n")
        f.write(d["summary"] + "\n\n")
        f.write("## Conversation Notes\n")
        for n in d["notes"]:
            f.write(f"- {n['time']}: {n['text']}\n")
        f.write("\n")
        if d["files"]:
            f.write("## Included files\n")
            for finfo in d["files"]:
                f.write(f"- {finfo['name']} ({finfo['size']} bytes)\n")
    # include a minimal Space config to be friendly
    with open(os.path.join(outroot, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"AO Drop {d['version']} — {d['title']}\n\n")
        f.write("This bundle is meant to be dropped into a Space root.\n")
    # copy attachments into /assets
    assets = os.path.join(outroot, "assets"); os.makedirs(assets, exist_ok=True)
    for finfo in d["files"]:
        shutil.copy2(finfo["path"], os.path.join(assets, finfo["name"]))
    # zip it
    outzip = os.path.join(HOME, f"AO_Drop_{d['version'].replace('/','_')}.zip")
    with zipfile.ZipFile(outzip, "w", zipfile.ZIP_DEFLATED) as z:
        for r,_,fs in os.walk(outroot):
            for fn in fs:
                ap = os.path.join(r, fn)
                z.write(ap, arcname=os.path.relpath(ap, outroot))
    return outzip, f"Built Drop zip with {len(d['files'])} file(s)."

with gr.Blocks(title="AO v0.7.0 — Drops") as demo:
    gr.Markdown(BANNER)
    with gr.Row():
        with gr.Column(scale=2):
            chat = gr.Chatbot(height=480, label="Chat")
            user = gr.Textbox(placeholder="Tell me what you want to build/change…")
            send = gr.Button("Send")
        with gr.Column(scale=1):
            gr.Markdown("### Draft Drop")
            version = gr.Textbox(value="v0.0.1", label="Version (semver or label)")
            title = gr.Textbox(label="Title")
            summary = gr.Textbox(lines=6, label="Summary / Release notes")
            files = gr.File(label="Attach files (multiple allowed)", file_count="multiple")
            attach_msg = gr.Textbox(label="Attachments status", interactive=False)
            build = gr.Button("Build Drop Zip")
            out_file = gr.File(label="Download Drop Zip")
            out_msg = gr.Markdown()
    state = gr.State(new_session())

    def _reset():
        return [("system", "Welcome to AO v0.7.0 — Drops mode. Tell me what you want; I can help you craft a Drop.")], "", new_session(), "v0.0.1", "", "", None, "Ready.", None, ""
    demo.load(_reset, outputs=[chat, user, state, version, title, summary, files, attach_msg, out_file, out_msg])

    send.click(chat_step, inputs=[chat, user, state], outputs=[chat, user, state])
    files.upload(receive_files, inputs=[files, state], outputs=[attach_msg, state])
    version.change(update_meta, inputs=[version, title, summary, state], outputs=state)
    title.change(update_meta, inputs=[version, title, summary, state], outputs=state)
    summary.change(update_meta, inputs=[version, title, summary, state], outputs=state)
    build.click(build_zip, inputs=state, outputs=[out_file, out_msg])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
