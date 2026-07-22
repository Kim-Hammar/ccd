FROM python:3.11-slim

# The SCADA command client is run on demand via `docker exec ... python3 /client.py`;
# the container itself just idles.
WORKDIR /app
COPY client.py /client.py
CMD ["sleep", "infinity"]
