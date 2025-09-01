import os, sys, json, time, re, shutil, yaml, gradio as gr

HOME_DIR = "/tmp/ao_home"
os.makedirs(HOME_DIR, exist_ok=True)
os.environ.setdefault("HOME", HOME_DIR)

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()

# --- Auto-detect HF namespace from SPACE_ID if not explicitly set ---
HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
SPACE_ID = os.environ.get("SPACE_ID", "").strip()  # e.g., "JmDrumsGarrison/AgentiveOrchestrator"
HF_NAMESPACE_SRC = "env"
if not HF_NAMESPACE and SPACE_ID and ("/" in SPACE_ID):
    HF_NAMESPACE = SPACE_ID.split("/")[0]
    HF_NAMESPACE_SRC = "SPACE_ID (auto)"
elif HF_NAMESPACE:
    HF_NAMESPACE_SRC = "HF_NAMESPACE (explicit)"
else:
    HF_NAMESPACE_SRC = "(unset)"

PORT = int(os.environ.get("PORT", "7860"))

FRIENDLY = (
    "👋 Hi, I’m AO — Agentic Orchestrator.\n\n"
    "Right now I specialize in **turning public GitHub repos into Hugging Face Spaces**.\n"
    "I always show a dry‑run plan and only execute after you confirm.\n\n"
    "Try:\n"
    "- what can you do right now?\n"
    "- show last job\n"
    "- create a space from https://github.com/owner/repo called aow-myspace on cpu\n"
)

def status():
    return {
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "HF_NAMESPACE_source": HF_NAMESPACE_SRC,
        "SPACE_ID": SPACE_ID or "(unset)",
        "build": "AO v0.6.0 (Docker, auto-detect namespace)"
    }

def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", (url or "").strip())
    if not m: return None, None
    return m.group(1), m.group(2)

# ---------- Repo IO helpers ----------
def _clone(work):
    from git import Repo
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    repo = Repo.clone_from(AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@"),
                           os.path.join(work, "repo"), depth=1)
    base = os.path.join(work, "repo")
    return repo, base

def _read(base, rel):
    p = os.path.join(base, rel)
    if not os.path.exists(p): return ""
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _append_logbook(title, plan, result):
    from git import Repo, Actor as A
    repo, base = _clone("/tmp/log_write")
    ops = os.path.join(base, "ops"); os.makedirs(ops, exist_ok=True)
    logp = os.path.join(ops, "logbook.md")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## {ts} — {title}\n\n**Plan**\n```yaml\n{yaml.safe_dump(plan, sort_keys=False)}\n```\n**Result**\n```json\n{json.dumps(result, indent=2)}\n```\n"
    mode = "a" if os.path.exists(logp) else "w"
    with open(logp, mode, encoding="utf-8") as f:
        if mode == "w": f.write("# AO Logbook\n")
        f.write(entry)
    repo.git.add([logp])
    author = A("AO Bot", "ao@example.com")
    repo.index.commit(f"chore(log): {title}", author=author, committer=author)
    repo.remotes.origin.push()

# ---------- Parsing / intents ----------
def _extract_fields(text: str):
    text = text or ""
    url_m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)
    repo_url = url_m.group(0) if url_m else ""
    name = ""
    m = re.search(r"\bname[:=]\s*([A-Za-z0-9_.\-]+)", text, re.I)
    if m: name = m.group(1)
    for pat in [r"\bcalled\s+([A-Za-z0-9_.\-]+)", r"\bcall\s+(?:it|this)\s+([A-Za-z0-9_.\-]+)", r"\bspace\s+name\s+is\s+([A-Za-z0-9_.\-]+)"]:
        mm = re.search(pat, text, re.I)
        if mm: name = mm.group(1)
    hw = "cpu-basic"
    if re.search(r"\bgpu\b|\bt4\b", text.lower()): hw = "t4-small"
    if "cpu" in text.lower(): hw = "cpu-basic"
    return {"repo_url": repo_url, "name": name, "hardware": hw}

def _intent(text: str):
    t = (text or "").lower()
    if any(k in t for k in ["log", "logs", "logbook", "last job", "history", "what happened today", "recent job"]):
        return "ask_logbook"
    if any(k in t for k in ["what can you do", "capabilities", "help"]):
        return "ask_context"
    if any(k in t for k in ["architecture", "plan", "how are you built", "how are you coded"]):
        return "ask_plan"
    if "github.com" in t and "space" in t or "github.com" in t and any(k in t for k in ["call", "name", "cpu", "gpu"]):
        return "create_space"
    if any(k in t for k in ["create a space", "create an hf space", "clone into a space", "make a space", "space from repo"]):
        return "create_space"
    return "chat"

# ---------- Execution ----------
def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

def _hf_headers():
    return {"Authorization": f"Bearer {HF_TOKEN}"}

def _execute_create_space(owner, plan):
    import requests
    from git import Repo
    if not GITHUB_TOKEN: return {"error": "GITHUB_TOKEN missing"}
    if not HF_TOKEN: return {"error": "HF_TOKEN missing"}

    # 1) Create GH repo (if needed)
    repo_name = plan["worker_repo"].split("/")[1]
    check = requests.get(f"https://api.github.com/repos/{owner}/{repo_name}", headers=_gh_headers(), timeout=30)
    if check.status_code == 200:
        gh = {"exists": True, "repo_url": f"https://github.com/{owner}/{repo_name}"}
    else:
        cr = requests.post("https://api.github.com/user/repos", headers=_gh_headers(),
                           json={"name": repo_name, "private": True, "auto_init": False}, timeout=30)
        if cr.status_code >= 300:
            return {"error": f"GitHub create failed: {cr.status_code} {cr.text[:200]}"}
        gh = {"created": True, "repo_url": f"https://github.com/{owner}/{repo_name}"}

    # 2) Seed from source
    work = "/tmp/seed"; 
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    try:
        src = Repo.clone_from(plan["repo_url"], os.path.join(work, "src"), depth=1)
        dst_auth = gh["repo_url"].replace("https://", f"https://{GITHUB_TOKEN}@")
        dst = Repo.clone_from(dst_auth, os.path.join(work, "dst"))
        for r,d,files in os.walk(os.path.join(work, "src")):
            if ".git" in r: continue
            rel = os.path.relpath(r, os.path.join(work, "src"))
            td = os.path.join(os.path.join(work, "dst"), rel); os.makedirs(td, exist_ok=True)
            for f in files:
                import shutil as sh; sh.copy2(os.path.join(r,f), os.path.join(td,f))
        dst.git.add(all=True)
        if dst.is_dirty():
            dst.index.commit("chore(seed): import from source repo")
            dst.remotes.origin.push()
        seed = {"seeded": True}
    except Exception as e:
        return {"error": f"Seeding failed: {e}"}

    # 3) Create HF Space
    ns = HF_NAMESPACE or owner
    payload = {"sdk": "docker", "private": True, "hardware": plan["hardware"], "repository": {"url": gh["repo_url"]}}
    import requests
    sr = requests.post(f"https://huggingface.co/api/spaces/{ns}/{repo_name}", headers=_hf_headers(), json=payload, timeout=60)
    if sr.status_code not in (200,201):
        return {"github": gh, "seed": seed, "space": {"error": f"HF create space failed: {sr.status_code} {sr.text[:200]}"}};
    sp = {"created": True, "space_id": f"{ns}/{repo_name}"}
    return {"github": gh, "seed": seed, "space": sp}

# ---------- Chat handlers ----------
def reset_chat():
    return [("", FRIENDLY)], "", {"pending":{}}

def step_chat(history, user_text, state):
    history = history or []
    state = state or {"pending":{}}
    pending = state.get("pending") or {}

    text = (user_text or "").strip()
    if not text:
        return history + [("","")], "", state

    intent = _intent(text)

    # Read-only answers
    if intent == "ask_context":
        try:
            _, base = _clone("/tmp/ao_read_ctx")
            ctx = _read(base, "ops/context.yaml")
            if not ctx: raise FileNotFoundError
            preview = "\n".join(ctx.splitlines()[:60])
            return history + [(text, f"Here’s my current context banner (from `ops/context.yaml`):\n\n> " + preview.replace("\n","\n> "))], "", state
        except Exception:
            return history + [(text, FRIENDLY)], "", state

    if intent == "ask_plan":
        try:
            _, base = _clone("/tmp/ao_read_plan")
            plan = _read(base, "ops/plan.md")
            if not plan:
                return history + [(text, "I couldn’t find `ops/plan.md` yet.")], "", state
            preview = "\n".join(plan.splitlines()[:80])
            return history + [(text, f"Plan preview (`ops/plan.md`):\n\n> " + preview.replace("\n","\n> "))], "", state
        except Exception as e:
            return history + [(text, f"I couldn’t load the plan yet ({e}).")], "", state

    if intent == "ask_logbook":
        try:
            _, base = _clone("/tmp/ao_read_log")
            log = _read(base, "ops/logbook.md")
            if not log:
                return history + [(text, "The logbook is empty so far.")], "", state
            sections = re.split(r"\n##\s+", log)
            last = sections[-1] if len(sections)>1 else log
            title, body = (last.split("\n",1)+[""])[:2]
            body_preview = body[:1000] + ("…" if len(body)>1000 else "")
            return history + [(text, f"**Most recent entry** — {title.strip()}\n\n{body_preview}")], "", state
        except Exception as e:
            return history + [(text, f"I couldn’t load the logbook yet ({e}).")], "", state

    if intent == "create_space":
        fields = _extract_fields(text)
        for k,v in fields.items():
            if v: pending[k]=v
        owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
        missing = [k for k in ["repo_url","name"] if not pending.get(k)]
        if not owner: missing.append("owner (set AO_DEFAULT_REPO)")
        if missing:
            example = "repo: https://github.com/owner/repo name: aow-myspace hardware: cpu-basic"
            return history + [(text, "Got it — I can create the Space, but I still need: " + ", ".join(missing) + f".\nFor example:\n`{example}`")], "", {"pending":pending}
        plan = {
            "intent": "create_space_from_repo",
            "repo_url": pending["repo_url"],
            "worker_repo": f"{owner}/{pending['name']}",
            "space_id": f"{HF_NAMESPACE or owner}/{pending['name']}",
            "hardware": pending.get("hardware","cpu-basic"),
        }
        history = history + [(text, "Here’s the plan (dry‑run):\n```yaml\n" + yaml.safe_dump(plan, sort_keys=False) + "```\nReply **yes** to proceed.")]
        if re.search(r"\b(yes|proceed|do it|go ahead)\b", text.lower()):
            result = _execute_create_space(owner, plan)
            try: _append_logbook("Create HF Space from GitHub repo", plan, result)
            except Exception: pass
            return history + [("", f"✅ Executed:\n```json\n{json.dumps(result, indent=2)}\n```")], "", {"pending":{}}
        pending["plan"]=plan
        return history, "", {"pending":pending}

    if re.search(r"\b(yes|proceed|do it|go ahead)\b", text.lower()) and state.get("pending",{}).get("plan"):
        plan = state["pending"]["plan"]
        owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
        result = _execute_create_space(owner, plan)
        try: _append_logbook("Create HF Space from GitHub repo", plan, result)
        except Exception: pass
        return history + [(text, f"✅ Executed:\n```json\n{json.dumps(result, indent=2)}\n```")], "", {"pending":{}}

    return history + [(text, "I can chat broadly, but my specialty today is turning a public GitHub repo into a Hugging Face Space. "
                              "Tell me the repo URL and a name (e.g., `name: aow-myspace`), and I’ll take it from there.")], "", state

with gr.Blocks(title="AO v0.6.0 — auto-detect namespace") as demo:
    gr.Markdown("## AO v0.6.0 — Conversational Space builder (auto‑detects HF namespace)\n")
    with gr.Tab("Status"):
        env = gr.JSON()
        demo.load(status, outputs=env)
    with gr.Tab("Jobs (conversational)"):
        chat = gr.Chatbot(height=480)
        txt = gr.Textbox(placeholder="Try: create a space from https://github.com/owner/repo called aow-myspace on cpu")
        send = gr.Button("Send")
        reset = gr.Button("Reset")
        state = gr.State({"pending":{}})
        demo.load(fn=reset_chat, outputs=[chat, txt, state])
        reset.click(fn=reset_chat, outputs=[chat, txt, state])
        send.click(fn=step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])
        txt.submit(fn=step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

