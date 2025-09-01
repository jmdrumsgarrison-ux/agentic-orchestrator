import os, sys, subprocess, json, time, re, shutil
import gradio as gr

OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")
GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
ALLOWLIST_REPOS = [s.strip() for s in os.environ.get("ALLOWLIST_REPOS","").split(",") if s.strip()]
PORT = int(os.environ.get("PORT", "7860"))

def status():
    return {
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "ALLOWLIST_REPOS": ALLOWLIST_REPOS,
        "python": sys.version.split()[0],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "build": "AO v0.3.0 (Docker)"
    }

def ask_chatgpt(question, context=""):
    if not OPENAI_API_KEY:
        return "[error] OPENAI_API_KEY not set in this container."
    import requests
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a concise engineering assistant. Answer clearly with concrete next steps when applicable."},
            {"role": "user", "content": f"Context:\n{context.strip()[:4000]}\n\nQuestion:\n{question}"}
        ],
        "temperature": 0.2,
    }
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload, timeout=60
        )
        if r.status_code == 429:
            try:
                detail = r.json()
            except Exception:
                detail = {"error": r.text[:400]}
            return "[openai error] 429 insufficient_quota — your API key's plan/quota is exhausted.\nDetails:\n" + json.dumps(detail, indent=2)
        if r.status_code != 200:
            return f"[openai error] {r.status_code} {r.text}"
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[exception] {e}"

# ---------- Read-only Git ----------
RO_WORKDIR = "/tmp/repo_ro"

def git_read(repo_url):
    try:
        os.makedirs(RO_WORKDIR, exist_ok=True)
    except Exception as e:
        return json.dumps({"error": f"Failed to create workdir {RO_WORKDIR}: {e}"}, indent=2)
    try:
        from git import Repo
    except Exception as e:
        return json.dumps({"error": f"GitPython import failed: {e}"}, indent=2)

    local = os.path.join(RO_WORKDIR, "repo")
    info = {"repo_url": repo_url, "workdir": RO_WORKDIR, "action": "", "error": None}
    try:
        if not repo_url or not repo_url.startswith("http"):
            raise ValueError("Please enter a full https repo URL, e.g. https://github.com/owner/repo")
        if os.path.exists(os.path.join(local, ".git")):
            repo = Repo(local)
            info["action"] = "fetch"
            repo.git.fetch("--depth=1", "origin")
            repo.git.checkout("FETCH_HEAD")
        else:
            src = repo_url.strip()
            if GITHUB_TOKEN and src.startswith("https://github.com/"):
                src = src.replace("https://", f"https://{GITHUB_TOKEN}@")
            info["action"] = "clone"
            repo = Repo.clone_from(src, local, depth=1)
        head = repo.head.commit
        info["head"] = {"sha": head.hexsha, "message": head.message.strip(), "author": str(head.author), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(head.committed_date))}
        try:
            info["branches"] = [h.name for h in repo.remotes.origin.refs][:10]
        except Exception:
            info["branches"] = []
        commits = []
        for c in repo.iter_commits(max_count=5):
            commits.append({"sha": c.hexsha, "msg": c.message.strip().splitlines()[0], "author": str(c.author), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(c.committed_date))})
        info["recent_commits"] = commits
        return json.dumps(info, indent=2)
    except Exception as e:
        info["error"] = str(e)
        return json.dumps(info, indent=2)

# ---------- Save Progress to Git (with empty-repo bootstrap) ----------
RW_WORKDIR = "/tmp/repo_rw"

def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        return None, None
    return m.group(1), m.group(2)

def _ensure_allowed(url: str):
    if not ALLOWLIST_REPOS:
        return True, None
    owner, repo = _owner_repo_from_url(url)
    if not owner:
        return False, "Repo URL must be like https://github.com/owner/repo"
    key = f"{owner}/{repo}"
    return (key in ALLOWLIST_REPOS), f"Repo {key} not in ALLOWLIST_REPOS: {ALLOWLIST_REPOS}"

def _repo_is_empty(repo):
    # A freshly created GitHub repo with no commits has no HEAD/refs
    try:
        if repo.head.is_valid():
            return False
    except Exception:
        pass
    # also check refs/heads
    try:
        return len(list(repo.refs)) == 0
    except Exception:
        return True

def save_progress(repo_url, branch, plan_text, log_text, dry_run=True, author_name="", author_email=""):
    ok, err = _ensure_allowed(repo_url)
    if not ok:
        return json.dumps({"error": err}, indent=2)
    if not GITHUB_TOKEN:
        return json.dumps({"error": "GITHUB_TOKEN not set; cannot push. Add it in Space secrets."}, indent=2)
    try:
        os.makedirs(RW_WORKDIR, exist_ok=True)
    except Exception as e:
        return json.dumps({"error": f"Failed to create workdir {RW_WORKDIR}: {e}"}, indent=2)

    from git import Repo, Actor, GitCommandError

    local = os.path.join(RW_WORKDIR, "repo")
    if os.path.exists(local):
        shutil.rmtree(local, ignore_errors=True)

    if not repo_url.startswith("https://github.com/"):
        return json.dumps({"error": "Only https://github.com URLs are supported."}, indent=2)

    src_auth = repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")

    try:
        repo = Repo.clone_from(src_auth, local, depth=1)
    except Exception as e:
        return json.dumps({"error": f"Clone failed: {e}"}, indent=2)

    initialized = False
    try:
        if _repo_is_empty(repo):
            # bootstrap: create orphan main branch and first commit
            repo.git.checkout("--orphan", "main")
            ops_dir = os.path.join(local, "ops")
            os.makedirs(ops_dir, exist_ok=True)
            with open(os.path.join(ops_dir, "plan.md"), "w", encoding="utf-8") as f:
                f.write(plan_text or "# Plan\n\n- initial goals / phases / acceptance\n")
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(os.path.join(ops_dir, "logbook.md"), "a", encoding="utf-8") as f:
                f.write(f"## {ts}\nInitialized AO logbook.\n")
            repo.git.add(all=True)
            if dry_run:
                diff_text = repo.git.diff("--cached")
                # reset index to leave repo pristine
                repo.git.reset()
                return json.dumps({
                    "repo": repo_url, "branch": "main (new)",
                    "workdir": RW_WORKDIR, "dry_run": True,
                    "bootstrap": True,
                    "changed_files": ["ops/plan.md", "ops/logbook.md"],
                    "diff_preview": diff_text
                }, indent=2)
            author = Actor(author_name or "AO Bot", author_email or "ao@example.com")
            repo.index.commit(f"chore(ops): bootstrap AO files")
            # set upstream and push first commit
            repo.git.push("--set-upstream", "origin", "main")
            head = repo.head.commit.hexsha
            initialized = True
            return json.dumps({
                "repo": repo_url, "branch": "main (new)",
                "workdir": RW_WORKDIR, "dry_run": False,
                "bootstrap": True,
                "committed": ["ops/plan.md", "ops/logbook.md"],
                "head": head
            }, indent=2)

        # Non-empty repo path (existing branch/commits)
        # determine branch
        target_branch = branch
        try:
            if not target_branch:
                for b in ["main", "master"]:
                    if b in repo.refs:
                        target_branch = b
                        break
            if target_branch:
                repo.git.checkout(target_branch)
        except Exception as e:
            return json.dumps({"error": f"Branch checkout failed: {e}"}, indent=2)

        ops_dir = os.path.join(local, "ops")
        os.makedirs(ops_dir, exist_ok=True)
        plan_path = os.path.join(ops_dir, "plan.md")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(plan_text or "# Plan\n\n- (fill me)\n")
        log_path = os.path.join(ops_dir, "logbook.md")
        with open(log_path, "a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n## {ts}\n")
            f.write((log_text or "Updated by AO.") + "\n")
        repo.git.add([plan_path, log_path])
        diff_text = repo.git.diff("--cached")
        if dry_run:
            repo.git.reset()
            return json.dumps({
                "repo": repo_url, "branch": target_branch or "(auto)",
                "workdir": RW_WORKDIR, "dry_run": True,
                "bootstrap": False,
                "changed_files": ["ops/plan.md", "ops/logbook.md"],
                "diff_preview": diff_text
            }, indent=2)
        author = Actor(author_name or "AO Bot", author_email or "ao@example.com")
        repo.index.commit(f"chore(ops): update plan/logbook via AO")
        repo.remotes.origin.push()
        head = repo.head.commit.hexsha
        return json.dumps({
            "repo": repo_url, "branch": target_branch or "(auto)",
            "workdir": RW_WORKDIR, "dry_run": False,
            "bootstrap": False,
            "committed": ["ops/plan.md", "ops/logbook.md"],
            "head": head
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Save failed: {e}", "initialized": initialized}, indent=2)

with gr.Blocks(title="Agentic Orchestrator (AO) v0.3.0 — Docker") as demo:
    gr.Markdown("## AO v0.3.0 — Docker\nGUI + ChatGPT + Read-only Git + **Save Progress to Git (now bootstraps empty repos)**")

    with gr.Tab("Status"):
        btn_stat = gr.Button("Check Status")
        out_stat = gr.JSON(label="Environment")
        btn_stat.click(fn=status, outputs=out_stat)
        demo.load(status, outputs=out_stat)

    with gr.Tab("Ask ChatGPT"):
        q = gr.Textbox(label="Question", placeholder="e.g., What are the next steps for deployment?")
        ctx = gr.Textbox(label="Optional context", lines=6, placeholder="Paste any relevant snippet here…")
        btn_ask = gr.Button("Ask")
        ans = gr.Textbox(label="Answer", lines=10)
        btn_ask.click(fn=ask_chatgpt, inputs=[q, ctx], outputs=ans)

    with gr.Tab("Git (read-only)"):
        url = gr.Textbox(label="Repository URL", placeholder="https://github.com/owner/repo")
        btn_git = gr.Button("Clone / Refresh (depth=1)")
        out_git = gr.Code(label="Repo Info (JSON)")
        btn_git.click(fn=git_read, inputs=url, outputs=out_git)

    with gr.Tab("Save Progress to Git"):
        gr.Markdown("Initialize empty repos or update existing ones with an `ops/` bundle. **Dry Run** shows diff without pushing.")
        s_repo = gr.Textbox(label="Repository URL", placeholder="https://github.com/owner/repo")
        s_branch = gr.Textbox(label="Branch (optional)", placeholder="main or master (auto / create for empty repo)")
        s_plan = gr.Textbox(label="ops/plan.md", lines=8, placeholder="# Plan\n\n- goals / phases / acceptance\n")
        s_log = gr.Textbox(label="ops/logbook.md (entry to append)", lines=6, placeholder="Initial log entry…")
        s_dry = gr.Checkbox(value=True, label="Dry Run (don't commit/push)", info="Shows diff; no changes pushed.")
        s_name = gr.Textbox(label="Commit author name (optional)")
        s_email = gr.Textbox(label="Commit author email (optional)")
        btn_save = gr.Button("Preview / Save")
        out_save = gr.Code(label="Result (JSON)")
        btn_save.click(fn=save_progress, inputs=[s_repo, s_branch, s_plan, s_log, s_dry, s_name, s_email], outputs=out_save)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

