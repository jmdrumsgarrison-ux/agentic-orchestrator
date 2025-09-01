import os, sys, json, time, re, shutil, yaml, gradio as gr

HOME_DIR = "/tmp/ao_home"
os.makedirs(HOME_DIR, exist_ok=True)
os.environ.setdefault("HOME", HOME_DIR)

GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()

# --- Auto-detect HF namespace from SPACE_ID if not explicitly set ---
HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
SPACE_ID = os.environ.get("SPACE_ID", "").strip()  # e.g., "user/space"
if not HF_NAMESPACE and SPACE_ID and ("/" in SPACE_ID):
    HF_NAMESPACE = SPACE_ID.split("/")[0]

PORT = int(os.environ.get("PORT", "7860"))

FRIENDLY = (
    "👋 Hi, I’m AO — Agentic Orchestrator.\n\n"
    "Chat with me about anything. When I recognize a supported action, I’ll show a **dry‑run plan** first and only run it after you say **yes**.\n\n"
    "I can:\n"
    "• Open Change Requests (CRs) and spin up Dev Spaces\n"
    "• Create Hugging Face Spaces from public GitHub repos\n"
    "• Show deployments and promote a CR to prod\n\n"
    "Try:\n"
    "• open a change request: add a deployments tab\n"
    "• create a space from https://github.com/owner/repo called aow-myspace on cpu\n"
    "• show deployments\n"
)

# ---------- Utilities ----------
def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\\.git)?/?$", (url or "").strip())
    if not m: return None, None
    return m.group(1), m.group(2)

def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

def _hf_headers():
    return {"Authorization": f"Bearer {HF_TOKEN}"}

# Git clone of AO repo
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

def _load_registry(base):
    ops = os.path.join(base, "ops"); os.makedirs(ops, exist_ok=True)
    rp = os.path.join(ops, "registry.json")
    if os.path.exists(rp):
        with open(rp, "r", encoding="utf-8") as f: return json.load(f)
    reg = {"prod": {}, "dev_spaces": [], "history": []}
    with open(rp, "w", encoding="utf-8") as f: json.dump(reg, f, indent=2)
    return reg

def _save_registry(base, reg):
    rp = os.path.join(base, "ops", "registry.json")
    with open(rp, "w", encoding="utf-8") as f: json.dump(reg, f, indent=2)

def _append_logbook(base, title, body):
    from git import Actor as A
    ops = os.path.join(base, "ops"); os.makedirs(ops, exist_ok=True)
    logp = os.path.join(ops, "logbook.md")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\\n## {ts} — {title}\\n\\n{body}\\n"
    mode = "a" if os.path.exists(logp) else "w"
    with open(logp, mode, encoding="utf-8") as f:
        if mode == "w": f.write("# AO Logbook\\n")
        f.write(entry)
    return logp

def _commit_and_push(repo, paths, msg):
    from git import Actor as A
    author = A("AO Bot", "ao@example.com")
    repo.git.add(paths)
    repo.index.commit(msg, author=author, committer=author)
    repo.remotes.origin.push()

# ---------- Space creation (seeded repo) ----------
def _gh_whoami():
    import requests
    me = requests.get("https://api.github.com/user", headers=_gh_headers(), timeout=30)
    if me.status_code==200: return me.json().get("login","unknown")
    return "unknown"

def _seed_new_repo_and_space(dev_repo_name, source_url):
    import requests
    from git import Repo, Actor as A
    author = A("AO Bot", "ao@example.com")

    cr = requests.post("https://api.github.com/user/repos", headers=_gh_headers(),
                       json={"name": dev_repo_name, "private": True, "auto_init": False}, timeout=30)
    if cr.status_code >= 300 and cr.status_code != 422:
        return {"error": f"GitHub create failed: {cr.status_code} {cr.text[:200]}"}
    gh_user = _gh_whoami()
    gh_url = f"https://github.com/{gh_user}/{dev_repo_name}"

    work = "/tmp/seed_dev"
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    src = Repo.clone_from(source_url, os.path.join(work, "src"), depth=1)
    dst = Repo.clone_from(gh_url.replace('https://', f'https://{GITHUB_TOKEN}@'), os.path.join(work, "dst"))
    for r,d,files in os.walk(os.path.join(work, "src")):
        if ".git" in r: continue
        rel = os.path.relpath(r, os.path.join(work, "src"))
        td = os.path.join(os.path.join(work, "dst"), rel); os.makedirs(td, exist_ok=True)
        for f in files:
            import shutil as sh; sh.copy2(os.path.join(r,f), os.path.join(td,f))
    dst.git.add(all=True)
    if dst.is_dirty():
        dst.index.commit("chore(seed): create dev repo from AO_DEFAULT_REPO", author=author, committer=author)
        dst.remotes.origin.push()

    sp_id = f"{HF_NAMESPACE}/{dev_repo_name}"
    payload = {"sdk": "docker", "private": True, "hardware": "cpu-basic", "repository": {"url": gh_url}}
    sr = requests.post(f"https://huggingface.co/api/spaces/{sp_id}", headers=_hf_headers(), json=payload, timeout=60)
    if sr.status_code not in (200,201):
        return {"github_repo": gh_url, "error": f"HF space create failed: {sr.status_code} {sr.text[:200]}"}
    return {"github_repo": gh_url, "space_id": sp_id}

# ---------- Parsing / intents ----------
def _extract_fields(text: str):
    text = text or ""
    url_m = re.search(r"https?://github\\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)
    repo_url = url_m.group(0) if url_m else ""
    name = ""
    m = re.search(r"\\bname[:=]\\s*([A-Za-z0-9_.\\-]+)", text, re.I)
    if m: name = m.group(1)
    for pat in [r"\\bcalled\\s+([A-Za-z0-9_.\\-]+)", r"\\bcall\\s+(?:it|this)\\s+([A-Za-z0-9_.\\-]+)", r"\\bspace\\s+name\\s+is\\s+([A-Za-z0-9_.\\-]+)"]:
        mm = re.search(pat, text, re.I)
        if mm: name = mm.group(1)
    hw = "cpu-basic"
    if re.search(r"\\bgpu\\b|\\bt4\\b", text.lower()): hw = "t4-small"
    if "cpu" in text.lower(): hw = "cpu-basic"
    return {"repo_url": repo_url, "name": name, "hardware": hw}

def _intent(text: str):
    t = (text or "").lower()
    if any(k in t for k in ["open a change request", "create change request", "new change request", "open cr"]):
        return "open_cr"
    if re.search(r"\\bpromote\\s+cr\\s+\\d+", t):
        return "promote_cr"
    if re.search(r"\\bdelete\\s+dev\\s+\\d+", t):
        return "delete_dev"
    if any(k in t for k in ["list deployments", "show deployments", "deployments", "show change requests"]):
        return "show_deployments"
    if any(k in t for k in ["log", "logs", "logbook", "last job", "recent job"]):
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

# ---------- Actions ----------
def _plan_card(title, summary_lines, plan_yaml=None, plan_json=None):
    md = f"### {title}\\n" + "\\n".join(f"- {l}" for l in summary_lines) + "\\n"
    if plan_yaml is not None:
        md += "\\n```yaml\\n" + plan_yaml + "\\n```\\n"
    if plan_json is not None:
        md += "\\n```json\\n" + plan_json + "\\n```\\n"
    md += "\\nReply **yes** to proceed."
    return md

def _create_cr(title, dry_run=True):
    if not AO_DEFAULT_REPO or not GITHUB_TOKEN or not HF_TOKEN:
        return {"error": "Missing AO_DEFAULT_REPO or tokens"}
    repo, base = _clone("/tmp/ao_cr")
    reg = _load_registry(base)
    next_id = 1 + max([int(x.get("cr_id","0")) for x in reg.get("dev_spaces",[])] + [int(reg.get("prod",{}).get("cr_id","0") or 0)])
    cr_id = f"{next_id:04d}"
    dev_repo_name = f"AgentiveOrchestrator-dev-{cr_id}"
    cr_yaml_path = os.path.join(base, "ops", "change_requests"); os.makedirs(cr_yaml_path, exist_ok=True)
    cr_file = os.path.join(cr_yaml_path, f"cr-{cr_id}.yaml")
    cr_yaml = {
        "cr_id": cr_id,
        "title": title,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dev_repo": dev_repo_name,
        "dev_space": f"{HF_NAMESPACE}/{dev_repo_name}",
        "status": "open"
    }
    if dry_run:
        return {"dry_run": True, "cr": cr_yaml}
    # Write CR file, commit
    with open(cr_file, "w", encoding="utf-8") as f: yaml.safe_dump(cr_yaml, f, sort_keys=False)
    logp = _append_logbook(base, f"Open CR {cr_id}", f"Title: {title}")
    _commit_and_push(repo, [cr_file, logp], f"chore(cr): open CR {cr_id}")
    # Seed new repo + space
    res = _seed_new_repo_and_space(dev_repo_name, AO_DEFAULT_REPO)
    if "error" in res:
        return {"cr": cr_yaml, "error": res["error"]}
    # Update registry
    reg["dev_spaces"].append({
        "cr_id": cr_id, "space": res["space_id"], "repo": res["github_repo"],
        "status": "running", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    _save_registry(base, reg)
    _commit_and_push(repo, [os.path.join(base,"ops","registry.json")], f"chore(registry): add dev space for CR {cr_id}")
    return {"cr": cr_yaml, "dev": res}

def _promote(cr_id):
    repo, base = _clone("/tmp/ao_promote")
    reg = _load_registry(base)
    entry = next((d for d in reg["dev_spaces"] if d["cr_id"]==cr_id), None)
    if not entry: return {"error": f"CR {cr_id} not found in dev_spaces"}
    prev = reg.get("prod",{})
    reg["history"].append(prev)
    reg["prod"] = {"space": entry["space"], "commit": "(n/a)", "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "cr_id": cr_id}
    _save_registry(base, reg)
    _commit_and_push(repo, [os.path.join(base,"ops","registry.json")], f"chore(promote): CR {cr_id} -> prod")
    return {"promoted_to": reg["prod"]}

def _delete_dev(cr_id):
    repo, base = _clone("/tmp/ao_deldev")
    reg = _load_registry(base)
    reg["dev_spaces"] = [d for d in reg["dev_spaces"] if d["cr_id"]!=cr_id]
    _save_registry(base, reg)
    _commit_and_push(repo, [os.path.join(base,"ops","registry.json")], f"chore(clean): remove dev entry for CR {cr_id}")
    return {"deleted_dev_for": cr_id}

def _get_registry_view():
    repo, base = _clone("/tmp/ao_view")
    reg = _load_registry(base)
    return reg

# ---------- Create Space from public repo (existing path) ----------
def _execute_create_space(owner, plan):
    import requests
    from git import Repo, Actor as A
    author = A("AO Bot", "ao@example.com")

    if not GITHUB_TOKEN: return {"error": "GITHUB_TOKEN missing"}
    if not HF_TOKEN: return {"error": "HF_TOKEN missing"}

    # 1) Create GH repo
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

    # 2) Seed
    work = "/tmp/seed"
    if os.path.exists(work): shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    src = Repo.clone_from(plan["repo_url"], os.path.join(work, "src"), depth=1)
    dst = Repo.clone_from(gh["repo_url"].replace("https://", f"https://{GITHUB_TOKEN}@"), os.path.join(work, "dst"))
    for r,d,files in os.walk(os.path.join(work, "src")):
        if ".git" in r: continue
        rel = os.path.relpath(r, os.path.join(work, "src"))
        td = os.path.join(os.path.join(work, "dst"), rel); os.makedirs(td, exist_ok=True)
        for f in files:
            import shutil as sh; sh.copy2(os.path.join(r,f), os.path.join(td,f))
    dst.git.add(all=True)
    if dst.is_dirty():
        dst.index.commit("chore(seed): import from source repo", author=author, committer=author)
        dst.remotes.origin.push()
    seed = {"seeded": True}

    # 3) Create HF Space
    ns = HF_NAMESPACE or owner
    payload = {"sdk": "docker", "private": True, "hardware": plan["hardware"], "repository": {"url": gh["repo_url"]}}
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

    # --- Always dry-run for actionable intents ---
    if intent == "open_cr":
        title = re.sub(r"open (a )?change request[:]?\s*", "", text, flags=re.I).strip() or "Unspecified change"
        plan = {"intent":"open_cr","title":title}
        card = _plan_card("Planned Change Request",
                          [f"Title: {title}", "Creates CR file, seeds Dev repo/Space, updates registry"],
                          plan_yaml=yaml.safe_dump(plan, sort_keys=False))
        pending["plan"]=plan
        return history + [(text, card)], "", {"pending":pending}

    if intent == "create_space":
        fields = _extract_fields(text)
        for k,v in fields.items():
            if v: pending[k]=v
        owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
        missing = [k for k in ["repo_url","name"] if not pending.get(k)]
        if not owner: missing.append("owner (set AO_DEFAULT_REPO)")
        if missing:
            example = "repo: https://github.com/owner/repo name: aow-myspace hardware: cpu-basic"
            return history + [(text, "Got it — I can create the Space, but I still need: " + ", ".join(missing) + f".\\nFor example:\\n`{example}`")], "", {"pending":pending}
        plan = {
            "intent": "create_space_from_repo",
            "repo_url": pending["repo_url"],
            "worker_repo": f"{owner}/{pending['name']}",
            "space_id": f"{HF_NAMESPACE or owner}/{pending['name']}",
            "hardware": pending.get("hardware","cpu-basic"),
        }
        card = _plan_card("Planned Space Creation",
                          [f"From repo: {plan['repo_url']}", f"As Space: {plan['space_id']}", f"Hardware: {plan['hardware']}"],
                          plan_yaml=yaml.safe_dump(plan, sort_keys=False))
        pending["plan"]=plan
        return history + [(text, card)], "", {"pending":pending}

    if intent == "promote_cr":
        m = re.search(r"promote\\s+cr\\s+(\\d+)", text.lower())
        cr_id = f"{int(m.group(1)):04d}" if m else None
        if not cr_id:
            return history + [(text, "I didn’t catch the CR number. Try: `promote cr 12`.")], "", state
        plan = {"intent":"promote","cr_id":cr_id}
        card = _plan_card("Planned Promotion",
                          [f"Promote CR: {cr_id} to prod"], plan_yaml=yaml.safe_dump(plan, sort_keys=False))
        pending["plan"]=plan
        return history + [(text, card)], "", {"pending":pending}

    if intent == "delete_dev":
        m = re.search(r"delete\\s+dev\\s+(\\d+)", text.lower())
        cr_id = f"{int(m.group(1)):04d}" if m else None
        if not cr_id:
            return history + [(text, "I didn’t catch the CR number. Try: `delete dev 12`.")], "", state
        plan = {"intent":"delete_dev","cr_id":cr_id}
        card = _plan_card("Planned Dev Cleanup",
                          [f"Remove Dev entry for CR: {cr_id} (registry only)"], plan_yaml=yaml.safe_dump(plan, sort_keys=False))
        pending["plan"]=plan
        return history + [(text, card)], "", {"pending":pending}

    # --- Confirm execution ---
    if re.search(r"\\b(yes|proceed|do it|go ahead)\\b", text.lower()) and state.get("pending",{}).get("plan"):
        plan = state["pending"]["plan"]
        if plan["intent"]=="open_cr":
            res = _create_cr(plan["title"], dry_run=False)
            return history + [(text, f"✅ Executed:\\n```json\\n{json.dumps(res, indent=2)}\\n```")], "", {"pending":{}}
        if plan["intent"]=="create_space_from_repo":
            owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
            res = _execute_create_space(owner, plan)
            try:
                repo, base = _clone("/tmp/ao_log_exec")
                logp = _append_logbook(base, "Create HF Space from GitHub repo", f"```json\\n{json.dumps(res, indent=2)}\\n```")
                _commit_and_push(repo, [logp], "chore(log): create space")
            except Exception:
                pass
            return history + [(text, f"✅ Executed:\\n```json\\n{json.dumps(res, indent=2)}\\n```")], "", {"pending":{}}
        if plan["intent"]=="promote":
            res = _promote(plan["cr_id"])
            return history + [(text, f"✅ Executed:\\n```json\\n{json.dumps(res, indent=2)}\\n```")], "", {"pending":{}}
        if plan["intent"]=="delete_dev":
            res = _delete_dev(plan["cr_id"])
            return history + [(text, f"✅ Executed:\\n```json\\n{json.dumps(res, indent=2)}\\n```")], "", {"pending":{}}

    # --- Read-only answers ---
    if intent == "show_deployments":
        reg = _get_registry_view()
        return history + [(text, "Deployments:\\n```json\\n" + json.dumps(reg, indent=2) + "\\n```")], "", state

    if intent == "ask_context":
        try:
            _, base = _clone("/tmp/ao_read_ctx")
            ctx = _read(base, "ops/context.yaml")
            if not ctx: raise FileNotFoundError
            preview = "\\n".join(ctx.splitlines()[:60])
            return history + [(text, f"Here’s my current context banner (from `ops/context.yaml`):\\n\\n> " + preview.replace("\\n","\\n> "))], "", state
        except Exception:
            return history + [(text, FRIENDLY)], "", state

    if intent == "ask_plan":
        try:
            _, base = _clone("/tmp/ao_read_plan")
            plan = _read(base, "ops/plan.md")
            if not plan:
                return history + [(text, "I couldn’t find `ops/plan.md` yet.")], "", state
            preview = "\\n".join(plan.splitlines()[:80])
            return history + [(text, f"Plan preview (`ops/plan.md`):\\n\\n> " + preview.replace("\\n","\\n> "))], "", state
        except Exception as e:
            return history + [(text, f"I couldn’t load the plan yet ({e}).")], "", state

    if intent == "ask_logbook":
        try:
            _, base = _clone("/tmp/ao_read_log")
            log = _read(base, "ops/logbook.md")
            if not log:
                return history + [(text, "The logbook is empty so far.")], "", state
            sections = re.split(r"\\n##\\s+", log)
            last = sections[-1] if len(sections)>1 else log
            title, body = (last.split("\\n",1)+[""])[:2]
            body_preview = body[:1000] + ("…" if len(body)>1000 else "")
            return history + [(text, f"**Most recent entry** — {title.strip()}\\n\\n{body_preview}")], "", state
        except Exception as e:
            return history + [(text, f"I couldn’t load the logbook yet ({e}).")], "", state

    # --- General chat fallback ---
    reply = ("I’m in open chat mode. Ask anything to refine ideas.\n\n"
             "When you want action, say something like:\n"
             "• open a change request: <title>\n"
             "• create a space from https://github.com/owner/repo called <name> on cpu")
    return history + [(text, reply)], "", state

# ---------- UI ----------
def ui_status():
    return {
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE or "(unset)",
        "SPACE_ID": SPACE_ID or "(unset)",
        "build": "AO v0.6.2 (Docker, always dry-run + open chat)"
    }

def ui_get_registry():
    return _get_registry_view()

def ui_promote(cr_id):
    return _promote(cr_id.strip())

def ui_delete_dev(cr_id):
    return _delete_dev(cr_id.strip())

with gr.Blocks(title="AO v0.6.2 — Open chat + Always dry-run") as demo:
    gr.Markdown("## AO v0.6.2 — Open chat by default; actionable steps always dry‑run first.\n")

    with gr.Tab("Status"):
        env = gr.JSON()
        demo.load(ui_status, outputs=env)

    with gr.Tab("Jobs (conversational)"):
        chat = gr.Chatbot(height=480)
        txt = gr.Textbox(placeholder="Try: open a change request: add a deployments tab")
        send = gr.Button("Send")
        reset = gr.Button("Reset")
        state = gr.State({"pending":{}})
        demo.load(fn=reset_chat, outputs=[chat, txt, state])
        reset.click(fn=reset_chat, outputs=[chat, txt, state])
        send.click(fn=step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])
        txt.submit(fn=step_chat, inputs=[chat, txt, state], outputs=[chat, txt, state])

    with gr.Tab("Deployments"):
        gr.Markdown("### Current Registry")
        reg = gr.JSON(label="registry.json")
        refresh = gr.Button("Refresh")
        with gr.Row():
            cr_id_input = gr.Textbox(label="CR ID", placeholder="e.g., 0001", scale=1)
            promote_btn = gr.Button("Promote to Prod", scale=1)
            delete_btn = gr.Button("Delete Dev (registry only)", scale=1)
        refresh.click(ui_get_registry, outputs=reg)
        promote_btn.click(ui_promote, inputs=cr_id_input, outputs=reg)
        delete_btn.click(ui_delete_dev, inputs=cr_id_input, outputs=reg)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

