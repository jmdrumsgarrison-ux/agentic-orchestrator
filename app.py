import os, io, shutil, zipfile, time, gradio as gr

PORT = int(os.environ.get("PORT","7860"))
HOME = "/tmp/ao_home"; os.makedirs(HOME, exist_ok=True)

CONTEXT = """\
# AO v0.7.3 — Drops Mode (Server-hosted)

Working agreement (seeded context):

- You = product owner/tester. You state problems or desired changes, and you provide logs/screenshots.
- AO = developer/maintainer. I deliver each new release as a fully packaged Drop (zip).
- Loop:
  1. You tell me the problem/feature.
  2. I package a new Drop (versioned zip).
  3. You deploy it in your Space.
  4. If errors, you send logs back.
  5. I patch and re-drop.
  6. Repeat until stable.
- Strict packaging: every change is a **full zip**, branded with the version. You don’t hand-edit.
- Communication style: concise back-and-forth, minimal explanations unless requested.
"""

def _ts(): return time.strftime("%Y-%m-%d %H:%M:%S")

def _init_state():
    return {
        "chat": [("system", CONTEXT)],
        "attachments": [],
        "version": "v0.7.3",
        "confirmed": False,
        "title": "",
        "summary": "",
    }

def reset_all():
    st = _init_state()
    welcome = "You’re in Drops mode. Describe what you want. When aligned, say **propose a Drop**. Upload logs/screenshots if needed. Say **yes** to build."
    return [("", welcome)], "", st, st["version"], "", ""

def _append(history, you=None, me=None):
    return history + [(you or "", me or "")]

def chat_step(history, user_text, st):
    history = history or []
    st = st or _init_state()
    msg = (user_text or "").strip()
    if not msg: return history, "", st
    lower = msg.lower()
    if "yes" in lower and "propose" not in lower:
        st["confirmed"] = True
        reply = f"Okay — I’ll package **AO_{st['version']}** now when you click Build."
        return _append(history, msg, reply), "", st
    if "propose a drop" in lower or "prepare a drop" in lower or "roll the next" in lower:
        reply = f"Proposing **AO_{st['version']}**. If that looks right, say **yes** to confirm."
        return _append(history, msg, reply), "", st
    canned = "Noted. When converged, say **propose a Drop** and then **yes** to build. Upload files anytime; they’ll be bundled."
    return _append(history, msg, canned), "", st

def set_meta(version, title, summary, st):
    st = st or _init_state()
    if version: st["version"] = version.strip()
    st["title"] = title or ""
    st["summary"] = summary or ""
    return st

def receive_files(files, st):
    st = st or _init_state()
    updir = os.path.join(HOME, "uploads"); os.makedirs(updir, exist_ok=True)
    added = []
    if files:
        for f in files:
            if not f: continue
            dst = os.path.join(updir, os.path.basename(f.name))
            shutil.copy2(f.name, dst)
            st["attachments"].append({"name": os.path.basename(dst), "path": dst, "size": os.path.getsize(dst)})
            added.append(os.path.basename(dst))
    return ("Attached: " + (", ".join(added) if added else "(none)")), st

def _write(history, st, outroot):
    with open(os.path.join(outroot, "DROP_NOTES.md"), "w", encoding="utf-8") as f:
        f.write(f"# AO {st['version']} — {st['title'] or 'Untitled'}\\n\\n")
        if st.get("summary"): f.write(st["summary"] + "\\n\\n")
        f.write("## Conversation\\n")
        for u,a in history or []:
            if u: f.write(f"- **You:** {u}\\n")
            if a: f.write(f"  - **AO:** {a}\\n")
        if st["attachments"]:
            f.write("\\n## Attachments\\n")
            for att in st["attachments"]:
                f.write(f"- {att['name']} ({att['size']} bytes)\\n")
    with open(os.path.join(outroot, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"AO {st['version']} — packaged Drop.\\nUnzip into your Space root.\\n")
    assets = os.path.join(outroot, "assets"); os.makedirs(assets, exist_ok=True)
    for att in st["attachments"]:
        shutil.copy2(att["path"], os.path.join(assets, att["name"]))

def build_zip(history, st):
    st = st or _init_state()
    if not st.get("confirmed"):
        return None, "Say **yes** to confirm building this Drop."
    outroot = os.path.join(HOME, "out"); shutil.rmtree(outroot, ignore_errors=True); os.makedirs(outroot, exist_ok=True)
    _write(history, st, outroot)
    safe = st["version"].replace("/", "_")
    zip_path = os.path.join(HOME, f"AO_{safe}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r,_,fs in os.walk(outroot):
            for fn in fs:
                ap = os.path.join(r, fn)
                z.write(ap, arcname=os.path.relpath(ap, outroot))
    st["confirmed"] = False
    return zip_path, f"Built AO_{safe}.zip."

with gr.Blocks(title="AO v0.7.3 — Drops") as demo:
    gr.Markdown(CONTEXT)
    with gr.Row():
        with gr.Column(scale=2):
            chat = gr.Chatbot(height=480, label="Chat")
            user = gr.Textbox(placeholder="Talk as usual: 'Propose a Drop', 'Yes', 'Here are logs'")
            send = gr.Button("Send")
        with gr.Column(scale=1):
            version = gr.Textbox(value="v0.7.3", label="Version (semver: vX.Y.Z)")
            title = gr.Textbox(label="Title (optional)")
            summary = gr.Textbox(lines=6, label="Summary (optional)")
            files = gr.File(label="Upload attachments", file_count="multiple")
            attach_status = gr.Textbox(label="Attachment status", interactive=False, value="Ready.")
            build = gr.Button("Build AO_<version>.zip")
            out_zip = gr.File(label="Download AO_<version>.zip")
            out_msg = gr.Markdown()

    state = gr.State(_init_state())

    def _boot():
        return [("", "AO v0.7.3 Drops mode. Same loop as here.")], "", _init_state(), "v0.7.3", "", ""
    demo.load(_boot, outputs=[chat, user, state, version, title, summary])

    send.click(chat_step, inputs=[chat, user, state], outputs=[chat, user, state])
    version.change(set_meta, inputs=[version, title, summary, state], outputs=state)
    title.change(set_meta, inputs=[version, title, summary, state], outputs=state)
    summary.change(set_meta, inputs=[version, title, summary, state], outputs=state)
    files.upload(receive_files, inputs=[files, state], outputs=[attach_status, state])
    build.click(build_zip, inputs=[chat, state], outputs=[out_zip, out_msg])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)
