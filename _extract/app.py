import os, sys, json, time, re, shutil
import gradio as gr
import yaml

# --- Hardening for slim containers ---
HOME_DIR = "/tmp/ao_home"
os.makedirs(HOME_DIR, exist_ok=True)
os.environ.setdefault("HOME", HOME_DIR)
os.environ.setdefault("GIT_AUTHOR_NAME", "AO Bot")
os.environ.setdefault("GIT_AUTHOR_EMAIL", "ao@example.com")
os.environ.setdefault("GIT_COMMITTER_NAME", os.environ.get("GIT_AUTHOR_NAME", "AO Bot"))
os.environ.setdefault("GIT_COMMITTER_EMAIL", os.environ.get("GIT_AUTHOR_EMAIL", "ao@example.com"))

# Secrets & config
OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")
GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
HF_TOKEN = SecretStrippedByGitPush"HF_TOKEN", "")
AO_DEFAULT_REPO = os.environ.get("AO_DEFAULT_REPO", "").strip()
AO_AUTO_COMMIT = os.environ.get("AO_AUTO_COMMIT", "true").lower() != "false"
JOBS_MAX_PER_DAY = int(os.environ.get("JOBS_MAX_PER_DAY", "3"))
HF_NAMESPACE = os.environ.get("HF_NAMESPACE", "").strip()
PORT = int(os.environ.get("PORT", "7860"))
STATE_FILE = "/tmp/ao_jobs_state.json"

# ---------------- Context Pack loader ----------------
def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", (url or "").strip())
    if not m: return None, None
    return m.group(1), m.group(2)

def _load_context_pack():
    # Try to read ops/context.yaml from AO_DEFAULT_REPO (via shallow clone)
    pack = {
        "intro": "I can provision worker repos, seed from GitHub, and create Hugging Face Spaces. I will show a dry‑run plan and only execute after your confirmation.",
        "capabilities": [
            "Create GitHub repo (private) under your org",
            "Seed from a public GitHub repo URL",
            "Create a Hugging Face Space from that repo (Docker SDK)",
            "Open PR-based change requests (coming soon)"
        ],
        "guardrails": [
            "Dry run by default; explicit yes/proceed required",
            f"Daily job cap (JOBS_MAX_PER_DAY={JOBS_MAX_PER_DAY})",
            f"HF namespace scoping (HF_NAMESPACE='{HF_NAMESPACE or '(unset)'}')"
        ],
        "examples": []
    }
    # Add dynamic examples based on available secrets
    owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
    if owner:
        pack["examples"].append(f'clone https://github.com/gaomingqi/Track-Anything into a new HF Space called aow-track-anything on cpu')
        pack["examples"].append(f'create a worker repo called aow-reranker')
        pack["examples"].append('open a change request to expose more controls')
    # Load override from repo if possible
    if not (GITHUB_TOKEN and AO_DEFAULT_REPO):
        return pack, False
    try:
        from git import Repo
        work = "/tmp/context_ro"
        if os.path.exists(work):
            shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        dst = Repo.clone_from(AO_DEFAULT_REPO.replace("https://", f"https://{GITHUB_TOKEN}@"), os.path.join(work, "repo"), depth=1)
        ctx_path = os.path.join(work, "repo", "ops", "context.yaml")
        if os.path.exists(ctx_path):
            with open(ctx_path, "r", encoding="utf-8") as f:
                user_pack = yaml.safe_load(f) or {}
            # merge with defaults
            for k in ["intro", "capabilities", "guardrails", "examples"]:
                if k in user_pack and user_pack[k]:
                    pack[k] = user_pack[k]
            return pack, True
    except Exception:
        pass
    return pack, False

# ---------------- Jobs state & rate limits ----------------
def _load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"jobs": [], "today": time.strftime("%Y-%m-%d"), "count": 0}

def _save_state(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f)
    except Exception:
        pass

def _rate_limit():
    s = _load_state()
    today = time.strftime("%Y-%m-%d")
    if s.get("today") != today:
        s = {"jobs": [], "today": today, "count": 0}
        _save_state(s)
    if s.get("count", 0) >= JOBS_MAX_PER_DAY:
        return False, f"Daily job limit reached ({JOBS_MAX_PER_DAY}). Try again tomorrow or raise JOBS_MAX_PER_DAY."
    return True, ""

def _record_job(job):
    s = _load_state()
    s["jobs"].append(job)
    s["count"] = s.get("count", 0) + 1
    _save_state(s)

# ---------------- Intent parsing & execution (same as 0.5.0) ----------------
def parse_intent(text: str):
    t = text.lower().strip()
    if "clone" in t and ("space" in t or "hugging face" in t):
        return "clone_repo_to_space"
    if "create" in t and "worker" in t and ("repo" in t or "repository" in t):
        return "create_worker_repo"
    if "change request" in t or "modify" in t or "patch" in t:
        return "change_request"
    if "space" in t and "repo" in t:
        return "clone_repo_to_space"
    return "clone_repo_to_space"

def extract_fields(text: str):
    url_m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)
    repo_url = url_m.group(0) if url_m else ""
    hw = "cpu-basic"
    if "t4" in text or "gpu" in text: hw = "t4-small"
    name = ""
    m1 = re.search(r"name[:=]\s*([A-Za-z0-9_.\-]+)", text)
    if m1: name = m1.group(1)
    m2 = re.search(r"called\s+([A-Za-z0-9_.\-]+)", text)
    if m2: name = m2.group(1)
    return {"repo_url": repo_url, "name": name, "hardware": hw}

def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}

def _hf_headers():
    return {"Authorization": f"Bearer {HF_TOKEN}"}

def create_github_repo(owner: str, name: str, private=True, dry_run=True):
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN missing"}
    url = f"https://api.github.com/repos/{owner}/{name}"
    import requests
    r = requests.get(url, headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        return {"exists": True, "repo_url": f"https://github.com/{owner}/{name}"}
    if dry_run:
        return {"dry_run": True, "action": "create_repo", "repo": f"{owner}/{name}"}
    r = requests.post(f"https://api.github.com/user/repos", headers=_gh_headers(),
                      json={"name": name, "private": private, "auto_init": False}, timeout=30)
    if r.status_code >= 300:
        return {"error": f"GitHub create failed: {r.status_code} {r.text[:200]}"}
    return {"created": True, "repo_url": f"https://github.com/{owner}/{name}"}

def seed_repo_from_github(dst_repo_url: str, src_repo_url: str, dry_run=True):
    from git import Repo
    work = "/tmp/seed"
    if os.path.exists(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    if dry_run:
        return {"dry_run": True, "action": "seed_repo", "src": src_repo_url, "dst": dst_repo_url}
    try:
        src = Repo.clone_from(src_repo_url, os.path.join(work, "src"), depth=1)
        dst_auth = dst_repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")
        dst = Repo.clone_from(dst_auth, os.path.join(work, "dst"))
        for root, dirs, files in os.walk(os.path.join(work, "src")):
            if ".git" in root: 
                continue
            rel = os.path.relpath(root, os.path.join(work, "src"))
            target_dir = os.path.join(work, "dst", rel)
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                import shutil as sh
                sh.copy2(os.path.join(root, f), os.path.join(target_dir, f))
        dst.git.add(all=True)
        if dst.is_dirty():
            dst.index.commit("chore(seed): import from source repo")
            dst.remotes.origin.push()
        return {"seeded": True}
    except Exception as e:
        return {"error": f"Seeding failed: {e}"}

def create_hf_space(space_id: str, repo_url: str, hardware: str, private=True, dry_run=True):
    if not HF_TOKEN:
        return {"error": "HF_TOKEN missing"}
    import requests
    owner = HF_NAMESPACE if HF_NAMESPACE else space_id.split("/")[0]
    name = space_id.split("/")[-1]
    payload = {"sdk": "docker", "private": private, "hardware": hardware, "repository": {"url": repo_url}}
    if dry_run:
        return {"dry_run": True, "action": "create_space", "space_id": f"{owner}/{name}", "hardware": hardware, "repo": repo_url}
    r = requests.post(f"https://huggingface.co/api/spaces/{owner}/{name}", headers=_hf_headers(), json=payload, timeout=60)
    if r.status_code in (200, 201):
        return {"created": True, "space_id": f"{owner}/{name}"}
    return {"error": f"HF create space failed: {r.status_code} {r.text[:200]}"}

def jobs_reset():
    pack, loaded = _load_context_pack()
    banner = "### What I can do now\n" + pack["intro"] + "\n\n" + \
             "**Capabilities**\n- " + "\n- ".join(pack["capabilities"]) + "\n\n" + \
             "**Guardrails**\n- " + "\n- ".join(pack["guardrails"]) + "\n"
    if pack["examples"]:
        banner += "\n**Try one:**\n- " + "\n- ".join(pack["examples"]) + "\n"
    return [("", banner)], ""

def parse_intent(text: str):
    t = text.lower().strip()
    if "clone" in t and ("space" in t or "hugging face" in t):
        return "clone_repo_to_space"
    if "create" in t and "worker" in t and ("repo" in t or "repository" in t):
        return "create_worker_repo"
    if "change request" in t or "modify" in t or "patch" in t:
        return "change_request"
    if "space" in t and "repo" in t:
        return "clone_repo_to_space"
    return "clone_repo_to_space"

def extract_fields(text: str):
    url_m = re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)
    repo_url = url_m.group(0) if url_m else ""
    hw = "cpu-basic"
    if "t4" in text or "gpu" in text: hw = "t4-small"
    name = ""
    m1 = re.search(r"name[:=]\s*([A-Za-z0-9_.\-]+)", text)
    if m1: name = m1.group(1)
    m2 = re.search(r"called\s+([A-Za-z0-9_.\-]+)", text)
    if m2: name = m2.group(1)
    return {"repo_url": repo_url, "name": name, "hardware": hw}

def _load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"jobs": [], "today": time.strftime("%Y-%m-%d"), "count": 0}

def _save_state(s):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f)
    except Exception:
        pass

def _rate_limit():
    s = _load_state()
    today = time.strftime("%Y-%m-%d")
    if s.get("today") != today:
        s = {"jobs": [], "today": today, "count": 0}
        _save_state(s)
    if s.get("count", 0) >= int(os.environ.get("JOBS_MAX_PER_DAY","3")):
        return False, f"Daily job limit reached ({os.environ.get('JOBS_MAX_PER_DAY','3')}). Try again tomorrow or raise JOBS_MAX_PER_DAY."
    return True, ""

def _record_job(job):
    s = _load_state()
    s["jobs"].append(job)
    s["count"] = s.get("count", 0) + 1
    _save_state(s)

def jobs_step(history, user_text):
    history = history or []
    user_text = (user_text or "").strip()
    if not user_text:
        return history + [("","")], ""

    ok, msg = _rate_limit()
    if not ok:
        return history + [(user_text, f"🛑 {msg}")], ""

    intent = parse_intent(user_text)
    fields = extract_fields(user_text)

    missing = []
    if intent in ("clone_repo_to_space", "create_worker_repo"):
        if not fields["name"]:
            missing.append("desired name (letters/numbers/dashes)")
    if intent == "clone_repo_to_space" and not fields["repo_url"]:
        missing.append("GitHub repo URL to clone from")

    owner, _ = _owner_repo_from_url(AO_DEFAULT_REPO)
    if not owner:
        missing.append("GitHub org/user (set AO_DEFAULT_REPO so I can infer it)")

    if missing:
        ask = "Got it. I still need: " + ", ".join(missing) + ". For example:\n" \
              f"`name: aow-track-anything repo: https://github.com/gaomingqi/Track-Anything`"
        return history + [(user_text, ask)], ""

    worker_repo = f"{owner}/{fields['name']}"
    worker_repo_url = f"https://github.com/{worker_repo}"

    plan_lines = [f"intent: {intent}", f"worker_repo: {worker_repo}"]
    if intent == "clone_repo_to_space":
        plan_lines += [f"seed_from: {fields['repo_url']}", f"space_id: {owner}/{fields['name']}", f"hardware: {fields['hardware']}"]
    plan = "\n".join(plan_lines)

    history = history + [(user_text, f"Here’s the plan (dry-run):\n```\n{plan}\n```\nReply **yes** to proceed or edit any field.")]
    if re.search(r"\b(yes|proceed|do it|go ahead)\b", user_text.lower()):
        result = jobs_execute(intent, owner, fields)
        _record_job({"intent": intent, "owner": owner, "fields": fields, "ts": time.time(), "result": result})
        return history + [("", f"✅ Executed:\n```json\n{json.dumps(result, indent=2)}\n```")], ""
    return history, ""

def jobs_execute(intent, owner, fields):
    from git import Repo
    # external API helpers nested to avoid top-level imports
    import requests

    def _gh_headers():
        return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    def _hf_headers():
        return {"Authorization": f"Bearer {HF_TOKEN}"}

    # Create GH repo
    def create_github_repo(owner: str, name: str, private=True):
        if not GITHUB_TOKEN:
            return {"error": "GITHUB_TOKEN missing"}
        url = f"https://api.github.com/repos/{owner}/{name}"
        r = requests.get(url, headers=_gh_headers(), timeout=30)
        if r.status_code == 200:
            return {"exists": True, "repo_url": f"https://github.com/{owner}/{name}"}
        r = requests.post(f"https://api.github.com/user/repos", headers=_gh_headers(),
                        json={"name": name, "private": private, "auto_init": False}, timeout=30)
        if r.status_code >= 300:
            return {"error": f"GitHub create failed: {r.status_code} {r.text[:200]}"}
        return {"created": True, "repo_url": f"https://github.com/{owner}/{name}"}

    # Seed
    def seed_repo(dst_repo_url: str, src_repo_url: str):
        work = "/tmp/seed"
        if os.path.exists(work):
            shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        try:
            src = Repo.clone_from(src_repo_url, os.path.join(work, "src"), depth=1)
            dst_auth = dst_repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")
            dst = Repo.clone_from(dst_auth, os.path.join(work, "dst"))
            for root, dirs, files in os.walk(os.path.join(work, "src")):
                if ".git" in root: 
                    continue
                rel = os.path.relpath(root, os.path.join(work, "src"))
                target_dir = os.path.join(work, "dst", rel)
                os.makedirs(target_dir, exist_ok=True)
                for f in files:
                    import shutil as sh
                    sh.copy2(os.path.join(root, f), os.path.join(target_dir, f))
            dst.git.add(all=True)
            if dst.is_dirty():
                dst.index.commit("chore(seed): import from source repo")
                dst.remotes.origin.push()
            return {"seeded": True}
        except Exception as e:
            return {"error": f"Seeding failed: {e}"}

    # Create HF space
    def create_space(space_id: str, repo_url: str, hardware: str, private=True):
        if not HF_TOKEN:
            return {"error": "HF_TOKEN missing"}
        owner_ns = HF_NAMESPACE if HF_NAMESPACE else space_id.split("/")[0]
        name = space_id.split("/")[-1]
        payload = {"sdk": "docker", "private": private, "hardware": hardware, "repository": {"url": repo_url}}
        r = requests.post(f"https://huggingface.co/api/spaces/{owner_ns}/{name}", headers=_hf_headers(), json=payload, timeout=60)
        if r.status_code in (200, 201):
            return {"created": True, "space_id": f"{owner_ns}/{name}"}
        return {"error": f"HF create space failed: {r.status_code} {r.text[:200]}"}

    if intent == "create_worker_repo":
        gh = create_github_repo(owner, fields["name"], private=True)
        return gh

    if intent == "clone_repo_to_space":
        gh = create_github_repo(owner, fields["name"], private=True)
        if "error" in gh:
            return gh
        dst_url = gh.get("repo_url", f"https://github.com/{owner}/{fields['name']}")
        seed = seed_repo(dst_url, fields["repo_url"])
        if "error" in seed:
            return seed
        space_id = f"{owner}/{fields['name']}"
        sp = create_space(space_id, dst_url, fields["hardware"], private=True)
        return {"github": gh, "seed": seed, "space": sp}

    if intent == "change_request":
        return {"todo": "CR scaffolding lands in v0.5.2 (branch+PR+sandbox)."}

# -------------- UI --------------
def status():
    return {
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "HF_TOKEN_present": bool(HF_TOKEN),
        "AO_DEFAULT_REPO": AO_DEFAULT_REPO,
        "HF_NAMESPACE": HF_NAMESPACE,
        "JOBS_MAX_PER_DAY": JOBS_MAX_PER_DAY,
        "build": "AO v0.5.1 (Docker Conversational + Context Packs)",
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    }

with gr.Blocks(title="AO v0.5.1 — Conversational + Context") as demo:
    gr.Markdown("## AO v0.5.1 — Conversational Jobs + Context Packs")
    with gr.Tab("Status"):
        env = gr.JSON(label="Environment")
        demo.load(status, outputs=env)

    with gr.Tab("Jobs (conversational)"):
        chat = gr.Chatbot(height=440)
        txt = gr.Textbox(placeholder="e.g., clone https://github.com/gaomingqi/Track-Anything into a new HF Space called aow-track-anything on cpu")
        send = gr.Button("Send")
        clear = gr.Button("Reset Context & Clear")

        # load banner on reset/load
        demo.load(fn=jobs_reset, outputs=[chat, txt])
        clear.click(fn=jobs_reset, outputs=[chat, txt])
        send.click(fn=jobs_step, inputs=[chat, txt], outputs=[chat, txt])
        txt.submit(fn=jobs_step, inputs=[chat, txt], outputs=[chat, txt])

    with gr.Tab("Save Progress (Auto)"):
        gr.Markdown("Your AO plan/log live in AO_DEFAULT_REPO. This tab remains minimal in 0.5.x.")
        out = gr.Code(label="Result (JSON)")
        def noop():
            return json.dumps({"ok": True, "note": "Use AO 0.3.x behavior already applied to your repo."}, indent=2)
        gr.Button("Run").click(noop, outputs=out)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

