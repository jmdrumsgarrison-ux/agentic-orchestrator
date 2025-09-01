import os

def synthesize_dockerfile(src_dir: str) -> str:
    req_name = None
    for name in ["requirements.txt", "requirements-prod.txt", "requirements_dev.txt"]:
        p = os.path.join(src_dir, name)
        if os.path.isfile(p):
            req_name = name
            break

    lines = []
    lines.append("# Synthesize Dockerfile (Drop51)")
    lines.append("FROM python:3.10-slim")
    lines.append("ENV DEBIAN_FRONTEND=noninteractive")
    lines.append("RUN apt-get update && apt-get install -y --no-install-recommends bash bash git tzdata gcc g++ pkg-config libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 ffmpeg && rm -rf /var/lib/apt/lists/*")
    lines.append("WORKDIR /workspace/app")
    lines.append("RUN useradd -m appuser && mkdir -p /workspace/app/user && chown -R appuser:appuser /workspace && chmod -R a+rwx /workspace")
    lines.append("ENV OMP_NUM_THREADS=1")
    lines.append("ENV PYTHONPATH=/workspace/app")
    lines.append("ENV CUDA_VISIBLE_DEVICES=0")
    lines.append("COPY . /workspace/app")
    lines.append('RUN python -c "import cv2" || pip install --no-cache-dir opencv-python-headless')
    lines.append("RUN pip install --no-cache-dir mmcv-lite")
    if req_name:
        lines.append(f"RUN sed -i '/mmcv/d' {req_name} && pip install --no-cache-dir -r {req_name}")
    else:
        lines.append("RUN pip install --no-cache-dir gradio fastapi uvicorn")
    lines.append("ENV FORCE_CUDA_DEVICE=0")
    # Use proper escaping for sed command inside CMD
    cmd_str = 'CMD ["bash", "-lc", "python -m pip list && sed -i \"s/cuda:3/cuda:0/g\" $(grep -rl \"cuda:3\" /workspace/app) || true && (python app.py || python main.py || python -m uvicorn app:app --host 0.0.0.0 --port 7860)"]'
    lines.append(cmd_str)
    return "\n".join(lines) + "\n"
