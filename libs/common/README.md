# libs/common (`farm-common`)

Shared Python package used by every service. Import it as `farm_common`.

| Module | What it gives you |
| --- | --- |
| `farm_common.app.create_app` | FastAPI app with `/health` and the shared setup |
| `farm_common.settings.ServiceSettings` | Database, RabbitMQ, Redis URLs and `root_path` from env vars |

Coming in issue #4: JWT verification and role checks, correlation-ID logging, standard error format,
RabbitMQ publish/consume helpers, outbox and processed-events tables.
