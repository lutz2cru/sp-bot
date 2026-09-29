FROM python:3.13-slim

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

# Volume persistant pour l'état des stocks
VOLUME ["/app/data"]

CMD ["python", "main.py", "run"]
