#!/bin/bash
set -e

echo "Migrating ChromaDB data to shared volume..."

docker-compose -f deploy/docker-compose.yaml stop tangerina-bot chromadb-viz 2>/dev/null || true

docker volume create tangerina-chromadb-data 2>/dev/null || echo "Volume already exists"

TEMP_DIR=$(mktemp -d)
echo "Copying data from bot container..."
docker cp tangerina-bot:/app/data/chromadb/. "$TEMP_DIR/" 2>/dev/null || echo "No existing data to copy (OK for first run)"

if [ "$(ls -A $TEMP_DIR 2>/dev/null)" ]; then
    echo "Copying data to shared volume..."
    docker run --rm -v tangerina-chromadb-data:/target -v "$TEMP_DIR:/source:ro" alpine sh -c "cp -r /source/* /target/ || true"
    echo "Data migrated successfully"
else
    echo "No existing data found (this is OK for first run)"
fi

rm -rf "$TEMP_DIR"

echo "Starting containers with shared volume..."
docker-compose -f deploy/docker-compose.yaml up -d tangerina-bot chromadb-viz

echo "Migration complete. Waiting for containers to be healthy..."
sleep 5
docker-compose -f deploy/docker-compose.yaml ps
