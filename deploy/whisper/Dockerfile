FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Keep Whisper downloads in a predictable, volume-mountable location
ENV XDG_CACHE_HOME=/app/.cache

# Default base config (can be overridden via env vars in docker-compose)
ENV WHISPER_MODEL=base
ENV WHISPER_LANGUAGE=pt

RUN pip install --no-cache-dir \
    flask \
    openai-whisper

COPY server.py /app/server.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/server.py /app/entrypoint.sh

EXPOSE 5002

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:5002/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "/app/server.py"]


