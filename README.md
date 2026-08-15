# AI API Gateway

Production-oriented implementation of candidate assignment 8: an API gateway
that authenticates clients by API key, applies a distributed request limit, and
proxies allowed requests to an external AI service.

## Selected assignment

**Assignment 8 - API gateway with rate limiting.**

The service will enforce a limit of five requests per minute for each client.
Requests above the limit will receive `429 Too Many Requests`.

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

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE).

