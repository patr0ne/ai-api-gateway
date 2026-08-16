# AI API Gateway

Production-oriented FastAPI gateway that authenticates clients by API key,
applies a distributed per-client request limit, and forwards allowed requests
to one server-configured AI provider.

Each client may make five requests during a 60-second fixed window. A sixth
request receives `429 Too Many Requests`; counters for different clients are
independent. PostgreSQL stores client records, Redis executes the atomic
rate-limit decision, and Alembic owns the database schema.

## Repository layout

```text
.
|-- .github/workflows/  # GitHub Actions checks
|-- docs/               # architecture and algorithm documentation
|-- migrations/         # Alembic environment and revisions
|-- src/                # application source code
|-- tests/              # unit and live integration tests
|-- Dockerfile
|-- compose.yaml
|-- LICENSE
|-- README.md
`-- pyproject.toml
```

The architecture, failure behavior, and rate-limit trade-offs are described in
[`docs/solution.md`](docs/solution.md).

## Run with Docker Compose

Copy `.env.example` to `.env` and replace every placeholder. The PostgreSQL
password must be URL-safe because it is included in the database URL. The
fingerprint pepper must contain at least 32 characters and remain stable: a
changed pepper invalidates all existing client-key fingerprints.

Build and start the complete environment:

```bash
docker compose up --build --wait
```

Compose starts healthy PostgreSQL and Redis services, runs `alembic upgrade
head` in the one-shot `migrate` container, and starts the gateway only after
the migration succeeds. The API is available at `http://127.0.0.1:8000` by
default, and its health endpoint is:

```bash
curl --fail http://127.0.0.1:8000/health
```

PostgreSQL data is stored in the named `postgres-data` volume. Stop containers
without deleting that data with:

```bash
docker compose down
```

Use the destructive variant only when local PostgreSQL data should be reset:

```bash
docker compose down --volumes
```

## Provision a client

The gateway stores only an HMAC-SHA256 fingerprint, never the plaintext API
key. Generate a random key and derive its fingerprint inside the running app
container:

```bash
docker compose exec app python -c "import secrets; from uuid import uuid4; from ai_api_gateway.auth import fingerprint_api_key; from ai_api_gateway.config import Settings; key=secrets.token_urlsafe(32); settings=Settings(); print('CLIENT_ID=' + str(uuid4())); print('CLIENT_API_KEY=' + key); print('KEY_FINGERPRINT=' + fingerprint_api_key(key, settings.api_key_fingerprint_pepper))"
```

Save `CLIENT_API_KEY` in the client's secret store; it is shown only once.
Insert the printed UUID and fingerprint, replacing the three example values:

```bash
docker compose exec postgres psql -U gateway -d gateway -c \
  "INSERT INTO api_clients (id, name, key_fingerprint) VALUES ('CLIENT_ID', 'local-demo', 'KEY_FINGERPRINT');"
```

If `POSTGRES_USER` or `POSTGRES_DB` was changed in `.env`, use the same values
in the `psql` command. Revoke a client without deleting it by setting
`is_active = false`.

## Call the gateway

`POST /v1/generate` accepts a JSON object and requires the client key in the
`X-API-Key` header. The gateway sends the payload only to the configured
provider's `generate` endpoint:

```bash
curl --include \
  --request POST http://127.0.0.1:8000/v1/generate \
  --header "Content-Type: application/json" \
  --header "X-API-Key: CLIENT_API_KEY" \
  --data '{"prompt":"Hello"}'
```

Successful and upstream-error responses include `X-RateLimit-Limit` and
`X-RateLimit-Remaining`. Repeating the request six times inside one minute
uses the five available attempts; the sixth response is `429` and also
includes `Retry-After`. An upstream failure still consumes an attempt so
provider outages cannot bypass protection.

## Local development and checks

Python 3.13 is required. Create a virtual environment and install the project
with its development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --editable ".[dev]"
```

In PowerShell, activate it with `.venv\Scripts\Activate.ps1` instead. Then run
the same quality checks as CI:

```bash
black --check .
flake8 src tests migrations
ruff check .
ruff format --check .
pyright --pythonpath "$(command -v python)"
python -m pytest -q -m "not integration"
```

For a direct host run, configure every `GATEWAY_` setting from `.env` and apply
the migration before starting Uvicorn:

```bash
python -m alembic upgrade head
python -m uvicorn ai_api_gateway.app:app --host 127.0.0.1 --port 8000
```

Live integration tests require disposable PostgreSQL and Redis instances. The
PostgreSQL database name must end in `_test`, and Redis must use a positive,
isolated database number because the fixtures truncate their own database and
flush their own Redis DB:

```bash
GATEWAY_DATABASE_DSN=postgresql://gateway:password@localhost:5432/gateway_test \
TEST_POSTGRES_DSN=postgresql://gateway:password@localhost:5432/gateway_test \
TEST_REDIS_URL=redis://localhost:6379/15 \
python -m alembic upgrade head

TEST_POSTGRES_DSN=postgresql://gateway:password@localhost:5432/gateway_test \
TEST_REDIS_URL=redis://localhost:6379/15 \
python -m pytest -q -m integration
```

Without both `TEST_POSTGRES_DSN` and `TEST_REDIS_URL`, integration tests are
skipped rather than mistaken for live-service verification.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request and contains
three jobs:

- **Quality and unit tests:** installs the development dependencies, checks
  them with `pip check`, runs Black, Flake8, Ruff, Pyright, and the non-live
  test suite.
- **PostgreSQL and Redis integration:** starts disposable service containers,
  checks the single Alembic head, upgrades an empty PostgreSQL database, and
  runs the tests marked `integration` against real PostgreSQL and Redis.
- **Docker Compose smoke test:** validates Compose configuration, builds the
  production image, waits for the complete environment, checks `/health`, and
  removes its containers, images, network, and test volume even after failure.

CI values are isolated test credentials. Repository secrets are not required
for the mocked upstream flow, and real provider credentials must never be
added to the workflow or committed to the repository.

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE).
