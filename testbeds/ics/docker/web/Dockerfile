FROM python:3.11-slim

# curl so icsctl can read /metrics and set the app mode via `docker exec ... curl localhost`
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY web.py ./
EXPOSE 8080
CMD ["python", "web.py"]
