import os, sys, json, time, re, shutil, yaml, gradio as gr

HOME_DIR = "/tmp/ao_home"
os.makedirs(HOME_DIR, exist_ok=True)
os.environ.setdefault("HOME", HOME_DIR)

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()

HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
SPACE_ID = os.environ.get("SPACE_ID", "").strip()
if not HF_NAMESPACE and SPACE_ID and ("/" in SPACE_ID):
    HF_NAMESPACE = SPACE_ID.split("/")[0]

PORT = int(os.environ.get("PORT", "7860"))

FRIENDLY = (
    "👋 Hi, I’m AO — Agentic Orchestrator.\n\n"
    "Talk to me about what you’d like to change or build. I’ll ask questions, refine the idea, "
    "and when it’s clear enough I’ll suggest drafting a Change Request (CR). "
    "You just confirm if you’re ready.\n\n"
    "I can also:\n"
    "• Create Hugging Face Spaces from public GitHub repos\n"
    "• Show deployments and promote a CR to prod\n\n"
    "Everything is dry-run first; nothing executes until you say yes.\n"
)

from git import Actor as A

def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\\.git)?/?$", (url or "").strip())
    if not m: return None, None
    return m.group(1), m.group(2)

def _gh_headers(): return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
def _hf_headers(): return {"Authorization": f"Bearer {HF_TOKEN}"}

def _clone(work):
    from git import Repo
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    repo = Repo.clone_from(AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@"),
                           os.path.join(work, "repo"), depth=1)
    base = os.path.join(work, "repo")
    return repo, base

def _append_logbook(base, title, body):
    ops = os.path.join(base, "ops"); os.makedirs(ops, exist_ok=True)
    logp = os.path.join(ops, "logbook.md")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\\n## {ts} — {title}\\n\\n{body}\\n"
    with open(logp, "a", encoding="utf-8") as f:
        if os.path.getsize(logp)==0: f.write("# AO Logbook\\n")
        f.write(entry)
    return logp

def _commit_and_push(repo, paths, msg):
    author = A("AO Bot", "ao@example.com")
    repo.git.add(paths)
    repo.index.commit(msg, author=author, committer=author)
    repo.remotes.origin.push()

def _create_cr(title, dry_run=True):
    repo, base = _clone("/tmp/ao_cr")
    cr_id = time.strftime("%Y%m%d%H%M%S")
    dev_repo_name = f"AgentiveOrchestrator-dev-{cr_id}"
    cr_yaml = {
        "cr_id": cr_id, "title": title,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dev_repo": dev_repo_name,
        "dev_space": f"{HF_NAMESPACE}/{dev_repo_name}",
        "status": "open"
    }
    if dry_run: return {"dry_run": True, "cr": cr_yaml}
    cr_path = os.path.join(base, "ops", "change_requests"); os.makedirs(cr_path, exist_ok=True)
    with open(os.path.join(cr_path, f"cr-{cr_id}.yaml"), "w") as f: yaml.safe_dump(cr_yaml, f)
    logp = _append_logbook(base, f"Open CR {cr_id}", f"Title: {title}")
    _commit_and_push(repo, [os.path.join(cr_path, f"cr-{cr_id}.yaml"), logp], f"chore(cr): open CR {cr_id}")
    return {"cr": cr_yaml}

def reset_chat():
    return [("", FRIENDLY)], "", {"pending":{"mode":None,"notes":[],"offered":False}}

def step_chat(history, user_text, state):
    history = history or []
    state = state or {"pending":{"mode":None,"notes":[],"offered":False}}
    pending = state["pending"]

    text = (user_text or "").strip()
    if not text: return history, "", state

    # --- If in CR discussion mode ---
    if pending.get("mode")=="cr_discuss":
        pending["notes"].append(text)
        # After 2-3 notes, AO suggests drafting
        if len(pending["notes"])>=2 and not pending.get("offered"):
            reply = ("I think we’ve got enough detail to formalize this as a Change Request.\n"
                     "Would you like me to draft it?")
            pending["offered"]=True
            return history+[(text,reply)], "", state
        else:
            return history+[(text,"Got it. Anything else you’d like to add?")], "", state

    # --- If confirming execution ---
    if re.search(r"\\b(yes|proceed|do it|go ahead)\\b", text.lower()) and pending.get("offered") and not pending.get("plan_executed"):
        title = " ".join(pending["notes"])[:100] or "Unspecified change"
        plan = {"intent":"open_cr","title":title}
        result = _create_cr(title, dry_run=False)
        state={"pending":{"mode":None,"notes":[],"offered":False,"plan_executed":True}}
        return history+[(text,f"✅ Executed:\\n```json\\n{json.dumps(result,indent=2)}\\n```")], "", state

    # --- Otherwise: detect change-y language and start CR discussion ---
    if any(w in text.lower() for w in ["change","modify","update","gui","tab","button","improve","add","remove"]):
        pending["mode"]="cr_discuss"
        pending["notes"]=[text]
        reply=("That sounds like a change we’d capture in a Change Request.\n"
               "Can you tell me more? For example:\n• What’s the goal?\n• Any must-haves?")
        return history+[(text,reply)], "", state

    # --- Default open chat ---
    return history+[(text,"Got it. I’ll note that down. Keep going.")], "", state

def ui_status():
    return {"AO_DEFAULT_REPO": AO_DEFAULT_REPO,
            "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
            "SPACE_ID": SPACE_ID or "(unset)",
            "build": "AO v0.6.4 (Docker, AO offers CR draft)"}

with gr.Blocks(title="AO v0.6.4") as demo:
    gr.Markdown("## AO v0.6.4 — Conversational CRs. AO suggests drafting when ready.\n")
    with gr.Tab("Status"):
        env = gr.JSON()
        demo.load(ui_status, outputs=env)
    with gr.Tab("Chat"):
        chat = gr.Chatbot(height=480)
        txt = gr.Textbox(placeholder="Tell me what you’d like to change or ask about…")
        send = gr.Button("Send")
        reset = gr.Button("Reset")
        state = gr.State({"pending":{"mode":None,"notes":[],"offered":False}})
        demo.load(fn=reset_chat, outputs=[chat, txt, state])
        reset.click(fn=reset_chat, outputs=[chat, txt, state])
        send.click(fn=step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])
        txt.submit(fn=step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])

if __name__=="__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

