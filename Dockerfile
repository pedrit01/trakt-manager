# Imagen de trakt-manager: por defecto arranca la API y la GUI web (`serve`) en el
# puerto 8000, y cualquier otro argumento ejecuta ese comando del CLI, por ejemplo:
#   docker compose run --rm trakt-manager sync lists/doomsday.yaml --dry-run
#
# Funciona sin .env: sin configuración arranca en modo configuración y la GUI
# (http://localhost:8000/) guía el resto. El código de configuración sale en los registros.

# --- 1. Construcción de la wheel (las herramientas de build no llegan a la imagen final) ---
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# --- 2. Imagen de ejecución ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Etiquetas OCI: Docker Desktop y GHCR las muestran. El flujo de publicación
# sobrescribe la versión y el origen con los del commit publicado.
LABEL org.opencontainers.image.title="trakt-manager" \
      org.opencontainers.image.description="Crea y sincroniza listas de Trakt desde una GUI web, una API HTTP o la línea de comandos." \
      org.opencontainers.image.source="https://github.com/pedrit01/trakt-manager" \
      org.opencontainers.image.licenses="NOASSERTION"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    LISTS_DIR=/app/lists \
    API_HOST=0.0.0.0 \
    API_PORT=8000

# Usuario sin privilegios. /data pertenece a él para que el volumen sea escribible:
# ahí se guardan el token, la configuración y las definiciones creadas desde la GUI.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/lists /app/lists \
    && chown -R app:app /data

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
