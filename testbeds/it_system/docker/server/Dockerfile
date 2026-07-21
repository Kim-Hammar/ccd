FROM python:3.11-slim

# iptables for link control (NET_ADMIN). If the nft backend misbehaves under Docker
# Desktop, switch to the legacy backend:
#   update-alternatives --set iptables /usr/sbin/iptables-legacy
RUN apt-get update \
    && apt-get install -y --no-install-recommends iptables curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 5000
ENTRYPOINT ["./entrypoint.sh"]
# single worker so the in-process counters stay coherent
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--bind", "0.0.0.0:5000", "app:app"]
