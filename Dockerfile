# Imagen de trakt-manager: por defecto arranca la API (`serve`), y cualquier
# otro argumento ejecuta ese comando del CLI, por ejemplo:
#   docker compose run --rm trakt-manager sync lists/doomsday.yaml --dry-run

# --- 1. Construcción de la wheel (las herramientas de build no llegan a la imagen final) ---
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# --- 2. Imagen de ejecución ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    LISTS_DIR=/app/lists \
    API_HOST=0.0.0.0 \
    API_PORT=8000

# Usuario sin privilegios. /data pertenece a él para que el volumen del token sea escribible.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /app/lists \
    && chown app:app /data

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

WORKDIR /app
# Definiciones incluidas por defecto; docker-compose monta encima ./lists para editarlas sin reconstruir.
COPY --chown=app:app lists ./lists

USER app
VOLUME ["/data"]
EXPOSE 8000

# Comprobación de salud con Python (la imagen slim no trae curl).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('API_PORT', '8000'), timeout=3)" || exit 1

ENTRYPOINT ["trakt-manager"]
CMD ["serve"]

# --- 3. Imagen de desarrollo: ejecuta los tests (docker compose run --rm tests) -------------
FROM python:3.12-slim AS dev
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"
COPY tests ./tests
COPY lists ./lists
ENTRYPOINT ["pytest"]
CMD ["-q"]
