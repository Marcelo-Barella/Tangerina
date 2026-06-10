FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
RUN pip install --no-cache-dir \
    torch==2.8.0 torchaudio==2.8.0 \
    --index-url ${TORCH_INDEX_URL} \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY model_loader.py quantize.py sanitize_text.py server.py entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh /app/server.py

ENV OMNIVOICE_PORT=5003
ENV OMNIVOICE_MODEL=k2-fsa/OmniVoice
ENV OMNIVOICE_PRECISION=int8
ENV OMNIVOICE_DEVICE=auto
ENV OMNIVOICE_NUM_STEP=16
ENV OMNIVOICE_SPEED=1.0
ENV OMNIVOICE_LOAD_ASR=false
ENV OMNIVOICE_INSTRUCT="female, brazilian accent"
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
ENV HF_HOME=/app/cache/huggingface

RUN mkdir -p /app/cache/huggingface

EXPOSE 5003

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=300s \
    CMD curl -f http://localhost:5003/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "/app/server.py"]
