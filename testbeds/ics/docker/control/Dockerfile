FROM python:3.11-slim

# iptables for the G2 gateway (NET_ADMIN); curl so icsctl can read /metrics and set the
# control mode via `docker exec ... curl localhost`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iptables curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY control.py entrypoint.sh ./
RUN chmod +x entrypoint.sh
EXPOSE 8080
ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "control.py"]
