# Agentic Orchestrator (AO) v0.1.0 — Docker

This package runs AO (GUI + Ask ChatGPT + Read-only Git) inside a Docker container.

## Features
- **GUI** (Gradio) with tabs: Status, Ask ChatGPT, Git (read-only)
- **Ask ChatGPT** using `OPENAI_API_KEY`
- **Read-only Git** using `gitpython`; supports private repos if `GITHUB_TOKEN` is provided

## Hugging Face Space (Docker SDK) Notes
- Build with this `Dockerfile`.
- The app listens on `0.0.0.0:$PORT` (Hugging Face injects `$PORT`). 
- Add secrets in Space settings → Variables and secrets:
  - `OPENAI_API_KEY` (required)
  - `GITHUB_TOKEN` (optional; for private repo reads)

## Local Run (optional)
```bash
docker build -t ao:0.1.0 .
docker run -p 7860:7860 -e OPENAI_API_KEY=sk-... -e GITHUB_TOKEN=ghp_... ao:0.1.0
# then open http://localhost:7860
```