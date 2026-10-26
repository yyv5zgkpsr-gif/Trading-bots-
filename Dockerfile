FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements-live.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-live.txt

COPY . .

# No default command: docker-compose.yml's two services each set their own
# (crypto_daemon.py for trading, robinhood_mcp.monitor for exit enforcement).
# Running the image with no override just prints crypto_daemon.py's --help.
CMD ["python", "crypto_daemon.py", "--help"]
