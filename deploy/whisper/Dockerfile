FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH=/app
ENV XDG_CACHE_HOME=/app/.cache
ENV WHISPER_MODEL=base
ENV WHISPER_LANGUAGE=pt

RUN pip install --no-cache-dir \
    flask \
    openai \
    openai-whisper

COPY features/__init__.py /app/features/__init__.py
COPY features/voice/__init__.py /app/features/voice/__init__.py
COPY features/voice/whisper_stt.py /app/features/voice/whisper_stt.py
COPY features/voice/openai_whisper_api.py /app/features/voice/openai_whisper_api.py
COPY deploy/whisper/server.py /app/server.py
COPY deploy/whisper/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/server.py /app/entrypoint.sh

EXPOSE 5002

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:5002/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "/app/server.py"]
