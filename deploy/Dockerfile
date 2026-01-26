FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --no-cache-dir \
    chromadb>=0.4.0 \
    sentence-transformers>=2.2.0

FROM base AS app

ARG WHISPER_PROVIDER

COPY requirements.txt requirements-test.txt ./

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-test.txt

RUN if [ "$WHISPER_PROVIDER" = "openai" ]; then \
    pip install --no-cache-dir openai-whisper; \
fi

COPY app.py flask_routes.py pytest.ini .coveragerc ./
COPY chatbot/ ./chatbot/
COPY features/ ./features/
COPY tests/ ./tests/

CMD ["python", "app.py"]

