FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps. sqlite3 ships with python; we only need build essentials for any
# wheels that lack prebuilt artifacts on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt /app/server/requirements.txt
RUN pip install -r /app/server/requirements.txt

COPY server /app/server

# Persistent volume mount target on Railway.
ENV OPENPOKE_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8001
CMD ["sh", "-c", "python -m server.server --host 0.0.0.0 --port ${PORT:-8001}"]
