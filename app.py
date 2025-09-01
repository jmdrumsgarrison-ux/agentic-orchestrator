import os, sys, subprocess, json, time
import gradio as gr

OPENAI_API_KEY = SecretStrippedByGitPush"OPENAI_API_KEY", "")
GITHUB_TOKEN = SecretStrippedByGitPush"GITHUB_TOKEN", "")
PORT = int(os.environ.get("PORT", "7860"))

def status():
    return {
        "OPENAI_API_KEY_present": bool(OPENAI_API_KEY),
        "GITHUB_TOKEN_present": bool(GITHUB_TOKEN),
        "python": sys.version.split()[0],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "build": "AO v0.1.2 (Docker Clean)"
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

WORKDIR = "/home/user/repo_ro"

def git_read(repo_url):
    try:
        os.makedirs(WORKDIR, exist_ok=True)
    except Exception as e:
        return json.dumps({"error": f"Failed to create workdir {WORKDIR}: {e}"}, indent=2)

    try:
        from git import Repo
    except Exception as e:
        return json.dumps({"error": f"GitPython import failed: {e}"}, indent=2)

    local = os.path.join(WORKDIR, "repo")
    info = {"repo_url": repo_url, "action": "", "error": None}
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

with gr.Blocks(title="Agentic Orchestrator (AO) v0.1.2 — Docker Clean") as demo:
    gr.Markdown("## AO v0.1.2 — Docker (Clean)\nGUI + ChatGPT + Read-only Git (writes to /home/user)")

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

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=PORT, show_error=True)

