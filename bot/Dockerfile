FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install build dependencies, install pip packages, then clean up to keep image small
RUN apt-get update && \
    apt-get install -y gcc python3-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY bot.py .

CMD ["python", "bot.py"]