# AI API Gateway

Production-oriented API gateway that authenticates clients by API key, applies
a distributed request limit, and proxies allowed requests to an external AI
service.

## Core behavior

The service enforces a limit of five requests per minute for each client.
Requests above the limit receive `429 Too Many Requests`.

## Engineering goals

- asynchronous HTTP API built with FastAPI;
- API-key storage in PostgreSQL;
- atomic distributed rate limiting in Redis;
- safe upstream proxying with explicit timeouts and error handling;
- automated tests, containerized local environment, and CI checks;
- documented architecture, algorithm, assumptions, and trade-offs.

## Repository layout

```text
.
|-- docs/           # architecture and algorithm documentation
|-- src/            # application source code
|-- tests/          # unit and integration tests
|-- LICENSE
|-- README.md
`-- pyproject.toml
```

Application code will be developed in a dedicated feature branch and merged
into `main` through explicit, reviewable commits.

## Local configuration

Copy `.env.example` to `.env` and replace every placeholder before starting
the application. Plain `postgresql://` database URLs are accepted and are
normalized to SQLAlchemy's asynchronous `postgresql+asyncpg://` driver.

The PostgreSQL schema is managed only through Alembic. With
`GATEWAY_DATABASE_DSN` configured, apply the current single migration head:

```bash
.venv/bin/python -m alembic upgrade head
```

The current implementation includes application configuration, the health
endpoint, the `api_clients` schema, API-key authentication, and an atomic Redis
fixed-window rate limiter. Authenticated and allowed `POST /v1/generate`
requests are forwarded only to the configured provider's `generate` endpoint;
provider timeouts and transport failures are returned as controlled gateway
errors.

## Tests

The default suite runs unit and mocked-transport tests. Live integration tests
are skipped unless both `TEST_POSTGRES_DSN` and `TEST_REDIS_URL` are supplied.
The PostgreSQL database name must end with `_test`, and the Redis URL must use
a non-zero database because integration fixtures clear their isolated state.

Apply the Alembic migration to the disposable database, then run:

```bash
TEST_POSTGRES_DSN=postgresql://gateway:password@localhost:5432/gateway_test \
TEST_REDIS_URL=redis://localhost:6379/15 \
.venv/bin/python -m pytest -q
```

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE).
