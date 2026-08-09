FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iptables curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir "aiohttp>=3.9"
COPY gateway.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "gateway.py"]
