FROM python:3.11-slim AS builder

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    python -m pip install .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local /usr/local
COPY .env.example ./

USER appuser

EXPOSE 8000

CMD ["uvicorn", "rulesgen.main:app", "--host", "0.0.0.0", "--port", "8000"]
