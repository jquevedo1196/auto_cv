# ═══════════════════════════════════════════════════════════════
#  Job Hunter Agent — Multi-stage Dockerfile
#  Stage 1: deps    → instala Poetry + dependencias Python
#  Stage 2: browser → instala Chromium + libs del sistema
#  Stage 3: runtime → imagen final mínima lista para producción
# ═══════════════════════════════════════════════════════════════

# ── Versions ────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.12
ARG POETRY_VERSION=1.8.3

# ════════════════════════════════════════════════════════════════
# STAGE 1 — deps
# Instala Poetry y resuelve dependencias Python en un venv aislado.
# Este stage se cachea mientras pyproject.toml / poetry.lock no cambien.
# ════════════════════════════════════════════════════════════════
FROM python:${PYTHON_VERSION}-slim AS deps

ARG POETRY_VERSION
ENV POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME=/opt/poetry \
    POETRY_VENV=/opt/poetry-venv \
    POETRY_CACHE_DIR=/opt/.cache \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    # instala el venv de la app en /opt/venv (separado de Poetry)
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/poetry-venv/bin:/opt/venv/bin:$PATH"

# Instalar Poetry en su propio venv (no contamina el sistema)
RUN python3 -m venv $POETRY_HOME \
    && $POETRY_HOME/bin/pip install --quiet --upgrade pip \
    && $POETRY_HOME/bin/pip install --quiet poetry==${POETRY_VERSION}

ENV PATH="${POETRY_HOME}/bin:${PATH}"

WORKDIR /build

# Copiar solo los archivos de dependencias primero → máximo cache hit
COPY pyproject.toml poetry.lock* ./

# Crear venv de la app e instalar solo dependencias de producción
RUN python3 -m venv $VIRTUAL_ENV \
    && poetry install --only=main --no-root --no-interaction --no-ansi


# ════════════════════════════════════════════════════════════════
# STAGE 2 — browser
# Instala Chromium y todas sus dependencias del sistema.
# Stage separado para que este layer pesado se cachee de forma
# independiente de los cambios en el código Python.
# ════════════════════════════════════════════════════════════════
FROM python:${PYTHON_VERSION}-slim AS browser

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

# Dependencias del sistema requeridas por Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core
    curl wget ca-certificates gnupg \
    # Chromium / rendering
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 \
    # Audio / fonts
    libasound2 libpango-1.0-0 libcairo2 \
    libfreetype6 libfontconfig1 \
    # Playwright needs these to run chromium --with-deps
    fonts-liberation libappindicator3-1 \
    && rm -rf /var/lib/apt/lists/*

# Copiar el venv ya construido desde el stage anterior
COPY --from=deps /opt/venv /opt/venv

# Instalar solo Chromium en una ruta dedicada (no en HOME del usuario)
RUN playwright install chromium --with-deps \
    && playwright install-deps chromium


# ════════════════════════════════════════════════════════════════
# STAGE 3 — runtime (imagen final)
# Copia solo lo necesario: venv, browsers, código fuente.
# Sin Poetry, sin cache de pip, sin herramientas de build.
# ════════════════════════════════════════════════════════════════
FROM python:${PYTHON_VERSION}-slim AS runtime

# ── Labels OCI ──────────────────────────────────────────────────
LABEL org.opencontainers.image.title="job-hunter-agent" \
      org.opencontainers.image.description="Automated DevOps/SRE job search agent" \
      org.opencontainers.image.authors="Jesús Enrique Quevedo Torres <jenriqueqt@gmail.com>" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/jenriqueqt/job-hunter-agent"

# ── Runtime env vars ─────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    # App config — override these at runtime (docker run -e / k8s secrets)
    ANTHROPIC_API_KEY="" \
    LINKEDIN_EMAIL="" \
    LINKEDIN_PASSWORD="" \
    GOOGLE_SHEET_ID="" \
    GOOGLE_SHEETS_CREDENTIALS=""

# Instalar solo las libs del sistema necesarias en runtime
# (subset de lo que instalamos en el stage browser)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libfreetype6 libfontconfig1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user ────────────────────────────────────────────────
RUN groupadd -g 1001 agent \
    && useradd -u 1001 -g agent -m -s /bin/bash agent

WORKDIR /app

# Copiar venv y browsers desde stages anteriores
COPY --from=deps   /opt/venv                /opt/venv
COPY --from=browser /opt/playwright-browsers /opt/playwright-browsers

# Copiar código fuente (este layer cambia frecuentemente — va al final)
COPY --chown=agent:agent . .

# Directorio para el CV PDF y sesión de LinkedIn
RUN mkdir -p assets logs \
    && chown -R agent:agent /app

USER agent

# ── Healthcheck ──────────────────────────────────────────────────
# Verifica que Python y el venv funcionan correctamente
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import anthropic, playwright, gspread; print('ok')" || exit 1

# ── Entrypoint ───────────────────────────────────────────────────
ENTRYPOINT ["python", "agent.py"]
CMD ["--dry-run"]