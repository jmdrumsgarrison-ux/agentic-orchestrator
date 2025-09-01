import os, sys, subprocess, json, time, re
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
        "build": "AO v0.2.0 (Docker)"
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

# ---------- Read-only Git (to /tmp/repo_ro) ----------
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

# ---------- Save Progress to Git (safe write) ----------
RW_WORKDIR = "/tmp/repo_rw"

def _owner_repo_from_url(url: str):
    m = re.match(r"https?://github.com/([^/]+)/([^/]+)(?:.git)?/?$", url.strip())
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

    # fresh clone for write ops
    local = os.path.join(RW_WORKDIR, "repo")
    if os.path.exists(local):
        # wipe to avoid mixing repos
        import shutil
        shutil.rmtree(local, ignore_errors=True)

    src = repo_url.strip()
    if src.startswith("https://github.com/"):
        src_auth = src.replace("https://", f"https://{GITHUB_TOKEN}@")
    else:
        return json.dumps({"error": "Only https://github.com/ URLs are supported in this build."}, indent=2)

    try:
        repo = Repo.clone_from(src_auth, local, depth=1)
    except Exception as e:
        return json.dumps({"error": f"Clone failed: {e}"}, indent=2)

    # choose branch
    try:
        if not branch:
            # try main then master
            for b in ["main", "master"]:
                if b in repo.refs:
                    branch = b
                    break
            if not branch:
                branch = repo.active_branch.name if not repo.head.is_detached else None
        if branch:
            repo.git.checkout(branch)
    except Exception as e:
        return json.dumps({"error": f"Branch checkout failed: {e}"}, indent=2)

    # create ops files
    ops_dir = os.path.join(local, "ops")
    os.makedirs(ops_dir, exist_ok=True)

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    # plan.md: overwrite with provided text (idempotent by content)
    plan_path = os.path.join(ops_dir, "plan.md")
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(plan_text or "# Plan\n\n- (fill me)\n")

    # logbook.md: append an entry
    log_path = os.path.join(ops_dir, "logbook.md")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n## {ts}\n")
        f.write((log_text or "Initialized AO logbook.") + "\n")

    repo.git.add([plan_path, log_path])

    # show diff (cached = staged)
    diff_text = repo.git.diff("--cached")

    if dry_run:
        # reset index so nothing remains staged
        repo.git.reset()
        return json.dumps({
            "repo": repo_url, "branch": branch or "(auto)",
            "workdir": RW_WORKDIR, "dry_run": True,
            "changed_files": ["ops/plan.md", "ops/logbook.md"],
            "diff_preview": diff_text
        }, indent=2)

    # real commit & push
    try:
        author = Actor(author_name or "AO Bot", author_email or "ao@example.com")
        repo.index.commit(f"chore(ops): update plan/logbook via AO @ {ts}", author=author, committer=author)
        repo.remotes.origin.push()  # uses token via remote URL
        head = repo.head.commit.hexsha
        return json.dumps({
            "repo": repo_url, "branch": branch or "(auto)",
            "workdir": RW_WORKDIR, "dry_run": False,
            "committed": ["ops/plan.md", "ops/logbook.md"],
            "head": head
        }, indent=2)
    except GitCommandError as ge:
        return json.dumps({"error": f"Push failed: {ge}"}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Commit failed: {e}"}, indent=2)

with gr.Blocks(title="Agentic Orchestrator (AO) v0.2.0 — Docker") as demo:
    gr.Markdown("## AO v0.2.0 — Docker\nGUI + ChatGPT + Read-only Git + **Save Progress to Git (safe)**")

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
        gr.Markdown("Write an `ops/` bundle to your repo with **Diff Preview** and **Dry Run**.")
        s_repo = gr.Textbox(label="Repository URL", placeholder="https://github.com/owner/repo")
        s_branch = gr.Textbox(label="Branch (optional)", placeholder="main or master (auto-detect if empty)")
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

