# xyberos-queues

**Message queue plugin — RFC-0019, M9.** Redis Streams, RabbitMQ, and Kafka
behind one `MessageQueue` contract (`publish` / `poll`).

## Install

```bash
pip install xyberos-queues             # from PyPI
pip install xyberos-queues[redis]      # optional drivers
pip install xyberos-queues[rabbitmq]
pip install xyberos-queues[kafka]

# development (editable, from this repo):
pip install -e ./queues
```

## Usage

```python
from xyberos import create_app
from xyberos_queues import QueuesPlugin

app = create_app()
app.load_plugin(QueuesPlugin(provider="redis"))     # or QUEUE_PROVIDER

app.tools.execute("queue_publish", None, topic="jobs", message="do work")
app.tools.execute("queue_poll", None, topic="jobs")     # -> "do work"
```

| Provider | Config |
| -------- | ------ |
| `redis` | Redis Streams (URL via `REDIS_URL`) |
| `rabbitmq` | host/port (default `localhost:5672`) |
| `kafka` | `bootstrap_servers` (default `localhost:9092`) |

`poll` drains one message (oldest first) per call; returns `None` when empty.

## Tests

```bash
pip install pytest fakeredis
pytest tests/
```

fakeredis + fake clients — no live brokers.

## Ship location

Plugin (`xyberos.plugins` entry point) — infrastructure queues (M9).
