FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget \
    tar \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN PIPER_VERSION="1.2.0" && \
    PIPER_ARCH="amd64" && \
    wget -q "https://github.com/rhasspy/piper/releases/download/v${PIPER_VERSION}/piper_${PIPER_ARCH}.tar.gz" -O /tmp/piper.tar.gz && \
    tar -xzf /tmp/piper.tar.gz -C /tmp && \
    cp /tmp/piper/piper /usr/local/bin/piper && \
    cp /tmp/piper/lib*.so* /usr/local/lib/ 2>/dev/null || true && \
    mkdir -p /usr/local/share/piper && \
    cp -r /tmp/piper/espeak-ng-data /usr/local/share/piper/ 2>/dev/null || true && \
    chmod +x /usr/local/bin/piper && \
    rm -rf /tmp/piper /tmp/piper.tar.gz && \
    ldconfig

RUN mkdir -p /app/models && \
    pip install --no-cache-dir flask

COPY server.py /app/server.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/server.py /app/entrypoint.sh

ENV PIPER_BIN=/usr/local/bin/piper
ENV PIPER_MODEL_PATH=/app/models/pt_BR-faber-medium.onnx
ENV ESPEAK_DATA=/usr/local/share/piper/espeak-ng-data

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:5001/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "/app/server.py"]

