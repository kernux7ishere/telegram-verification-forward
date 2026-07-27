# Optional container image. Render uses the native Python runtime
# (see render.yaml); this is for local runs and other hosts.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

WORKDIR /app

# curl is needed for the container healthcheck and the Doppler installer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: bake in the Doppler CLI so `doppler run` works inside the image.
RUN curl -sLf --retry 3 https://cli.doppler.com/install.sh | sh || \
    echo "Doppler CLI unavailable; falling back to environment variables"

COPY . .
RUN chmod +x scripts/*.sh && mkdir -p data logs

# Drop privileges — nothing here needs root at runtime.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

CMD ["./scripts/start.sh"]
