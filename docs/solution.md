# Assignment 8: AI API Gateway

## 1. Scope

The selected assignment is **Assignment 8: an API gateway with rate limiting**.
Assignment 9 is not implemented as a separate product: its Docker Compose and
CI/CD requirements are used to package and verify the gateway.

The service accepts authenticated requests, limits every client to five
requests during a 60-second window, and forwards allowed requests to one
configured AI provider. It is deliberately not a general-purpose HTTP proxy:
the upstream base URL and endpoint are controlled by server configuration.

## 2. Main requirements

- authenticate a client by an API key;
- keep client records in PostgreSQL;
- enforce the limit atomically in Redis;
- return `429 Too Many Requests` after five requests in a window;
- proxy an allowed request to the configured AI service;
- run the application, PostgreSQL, and Redis through Docker Compose;
- run formatting, linting, and tests in CI;
- never store or log plaintext API keys or upstream credentials.

## 3. Request flow

1. A client sends `POST /v1/generate` with an API key in the
   `X-API-Key` header.
2. The gateway derives a deterministic fingerprint from the key and looks up
   an active client in PostgreSQL.
3. Redis increments that client's counter and sets its expiry as one atomic
   operation.
4. If the counter is greater than five, the gateway returns `429` with a
   `Retry-After` header and does not contact the AI provider.
5. Otherwise, the gateway forwards the validated JSON body to the configured
   upstream endpoint with an explicit timeout.
6. The upstream status and body are returned to the client. Transport errors
   are translated into a controlled gateway response.

The counter is updated before the upstream call. Therefore, an upstream
failure still consumes one request from the current window. This protects the
provider from retry storms and keeps the algorithm simple and deterministic.

## 4. Components

### FastAPI application

The HTTP layer owns request validation, dependency wiring, error mapping, and
response headers. Configuration is loaded from environment variables and
validated when the application starts.

### PostgreSQL

PostgreSQL is the source of truth for clients. The initial schema contains an
`api_clients` table with these fields:

- `id`: UUID primary key;
- `name`: human-readable unique name;
- `key_fingerprint`: unique indexed API-key fingerprint;
- `is_active`: allows revocation without deleting audit-relevant data;
- `created_at`: creation timestamp.

API keys are generated as high-entropy random values. The stored fingerprint
is `HMAC-SHA256(secret_pepper, api_key)`. This allows indexed lookup while the
plaintext key remains unrecoverable without both the original key and the
server-side pepper. The raw key must only be shown once when it is created.

### Redis

Redis stores short-lived counters only; PostgreSQL client data is not copied
into Redis in the first version. A counter key is scoped by client identifier:

```text
rate_limit:{client_id}
```

The first accepted attempt starts a 60-second fixed window. Redis removes the
key automatically when the window expires.

### AI provider client

One reusable asynchronous HTTP client is created for the application
lifecycle. The client uses a configured base URL, provider credential, and
timeouts. Restricting the destination prevents the gateway from becoming an
open proxy or an SSRF primitive.

## 5. Rate-limiting algorithm

The fixed-window counter is implemented as a Redis Lua script so incrementing
the value and setting its expiry cannot be separated by a concurrent request
or process failure.

Pseudo-code:

```text
current = INCR key

if current == 1:
    EXPIRE key 60

ttl = TTL key
allowed = current <= 5

return allowed, current, ttl
```

Every application replica runs the same script against Redis, so the decision
does not depend on in-process state. The response includes:

- `X-RateLimit-Limit: 5`;
- `X-RateLimit-Remaining: max(0, 5 - current)`;
- `Retry-After: ttl` for a rejected request.

The fixed-window approach can allow a burst immediately after a previous
window expires. A sliding window or token bucket would smooth such bursts but
would add data and algorithmic complexity that the assignment does not
require.

## 6. Failure handling

- Missing, invalid, or revoked API key: `401 Unauthorized` with no detail that
  helps enumerate clients.
- PostgreSQL unavailable: `503 Service Unavailable`; authentication cannot be
  established safely.
- Redis unavailable: `503 Service Unavailable`; the gateway fails closed to
  avoid unbounded provider usage and cost.
- Rate limit exceeded: `429 Too Many Requests`.
- Upstream connection or protocol failure: `502 Bad Gateway`.
- Upstream timeout: `504 Gateway Timeout`.
- Invalid client payload: `422 Unprocessable Entity` from request validation.

Logs contain a request ID, client ID after successful authentication, latency,
and outcome. They must not contain API keys, provider credentials, or full
request and response bodies.

## 7. Docker and CI

Docker Compose will start three services:

- `app`: the FastAPI gateway;
- `postgres`: persistent client storage with a health check;
- `redis`: rate-limit storage with a health check.

The application starts only after its dependencies are healthy and database
migrations have completed. Secrets are supplied through environment variables;
the repository contains only an `.env.example` with non-secret placeholders.

GitHub Actions will install the project and run the same commands used locally:

1. formatting check;
2. linting;
3. type checking;
4. unit and integration tests.

## 8. Test strategy

Unit tests cover configuration validation, API-key fingerprinting, rate-limit
decisions, header calculation, and upstream error mapping. Integration tests
cover PostgreSQL client lookup, the real Redis Lua script, and the complete
FastAPI request flow with a mocked upstream service.

Important boundary cases are:

- the first five requests are allowed and the sixth returns `429`;
- counters are isolated by client;
- the limit resets after expiry;
- simultaneous requests cannot bypass the limit;
- a revoked key is rejected;
- Redis or PostgreSQL failure does not silently disable protection;
- timeout and connection failures never expose internal exception details.

## 9. Implementation sequence

The work is intentionally split into reviewable commits:

1. document architecture and rate-limiting decisions;
2. add application configuration and health endpoint;
3. add PostgreSQL model, migration, and API-key authentication;
4. add the atomic Redis rate limiter;
5. add safe upstream proxying and HTTP error mapping;
6. add Docker image and Docker Compose environment;
7. add the complete test suite and GitHub Actions workflow;
8. finish operational documentation and usage examples.

## 10. Acceptance criteria

The implementation is complete when a clean checkout can be started through
Docker Compose, a valid client can make exactly five requests within a window,
the sixth request returns `429`, another client has an independent counter,
and all local and CI checks pass.

