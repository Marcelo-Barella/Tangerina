FROM python:3.11-slim

WORKDIR /app

ARG WHISPER_PROVIDER

RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN if [ "$WHISPER_PROVIDER" = "openai" ]; then \
    pip install --no-cache-dir openai-whisper; \
fi

COPY app.py flask_routes.py ./
COPY chatbot/ ./chatbot/
COPY features/ ./features/

CMD ["python", "app.py"]

