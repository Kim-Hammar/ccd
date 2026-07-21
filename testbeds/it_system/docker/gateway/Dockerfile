FROM python:3.11-slim

# iptables for link control (NET_ADMIN). If the nft backend misbehaves under Docker
# Desktop, switch to the legacy backend:
#   update-alternatives --set iptables /usr/sbin/iptables-legacy
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
