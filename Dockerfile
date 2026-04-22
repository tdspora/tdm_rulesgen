FROM python:3.11-slim AS builder

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    python -m pip install ".[api]"

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOME=/home/appuser
ENV RULESGEN_DATA_DIR=/home/appuser/.rulesgen-data
ENV RULESGEN_RULES_REPOSITORY_DIR=/home/appuser/.rulesgen-data/rules
ENV RULESGEN_JOBS_REPOSITORY_DIR=/home/appuser/.rulesgen-data/jobs
ENV RULESGEN_ARTIFACTS_REPOSITORY_DIR=/home/appuser/.rulesgen-data/artifacts
ENV RULESGEN_UPLOADS_REPOSITORY_DIR=/home/appuser/.rulesgen-data/uploads
ENV RULESGEN_AUDITS_REPOSITORY_DIR=/home/appuser/.rulesgen-data/audits
ENV RULESGEN_OSSFS_ROOT_DIR=/home/appuser/.rulesgen-data/ossfs
ENV RULESGEN_SANDBOX_WORKSPACE_DIR=/home/appuser/.rulesgen-data/opensandbox

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local /usr/local
COPY .env.example ./
COPY docker/entrypoint.py /usr/local/bin/rulesgen-entrypoint.py

RUN chmod 755 /usr/local/bin/rulesgen-entrypoint.py

EXPOSE 8000

ENTRYPOINT ["python", "/usr/local/bin/rulesgen-entrypoint.py"]
CMD ["uvicorn", "rulesgen.main:app", "--host", "0.0.0.0", "--port", "8000"]
