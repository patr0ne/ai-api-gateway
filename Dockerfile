FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip wheel --wheel-dir /wheels .


FROM python:3.13-slim AS runtime

ENV PATH="/home/gateway/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 gateway

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --find-links=/wheels ai-api-gateway==0.1.0 \
    && rm -rf /wheels

WORKDIR /app

COPY alembic.ini ./
COPY migrations ./migrations

USER gateway

EXPOSE 8000

CMD ["uvicorn", "ai_api_gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
