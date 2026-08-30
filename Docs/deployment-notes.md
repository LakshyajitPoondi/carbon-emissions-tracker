# Deployment notes

Operational settings that are not expressible in the repository, or that are
easy to lose when they live only in a hosting dashboard.

## Railway: the Celery worker start command

The worker service **must** be started with:

```
celery -A app.celery_app worker --loglevel=info \
  --concurrency=2 --max-tasks-per-child=100 \
  --without-gossip --without-mingle --without-heartbeat
```

### Why `--concurrency=2` is not optional

Celery's prefork pool defaults its concurrency to **the CPU count the
container can see**, which on a managed platform is the *host's* core count,
not the share of the machine the plan actually bought. On a 16-core host the
worker forks 16 children plus a parent.

Measured, on the same image and code, using the cgroup counter that a memory
limit actually enforces:

| Concurrency | Processes | cgroup memory |
| --- | --- | --- |
| 16 (the default) | 1 + 16 | **704.6 MB** |
| 2 (this setting) | 1 + 2 | **142.8 MB** |

Against Railway's 500 MB limit, the default is a guaranteed OOM — the worker
dies during startup, and report generation sits in `PENDING` forever because
nothing is alive to consume the queue.

**This is not caused by machine-learning imports.** That was the original
hypothesis and it was investigated and refuted: the worker's import graph is
`app.celery_app → app.tasks → {database, models, pubsub, services.reports,
ws}` and contains no `app.ml`, no torch, no OpenCV, no ultralytics. Verified
both by `sys.modules` after a cold import and by checking `/proc/<pid>/maps`
of every live worker process for the mapped shared objects. `tests/
test_celery_imports.py` locks that property in so a future import cannot
quietly reintroduce a real import-driven OOM on top of this one.

The other flags are secondary: `--max-tasks-per-child=100` recycles a child
periodically so a slow leak cannot climb back to the ceiling, and
`--without-gossip --without-mingle --without-heartbeat` drop inter-worker
coordination traffic that has no purpose in a single-worker deployment.

### Where this command is configured

> [!IMPORTANT]
> **Railway does not read `docker-compose.yml`.** The compose file configures
> local development only. Changing it does not change what Railway runs.

There is deliberately no `railway.json`, `railway.toml`, `Procfile`, or
nixpacks config in this repository, so the worker's Railway start command is
set **in the Railway dashboard**, under the worker service's
Settings → Deploy → Start Command.

That matters for two reasons:

1. **A dashboard Start Command overrides the image's `CMD`.** If one is set —
   and for this project one must be, because the backend and worker services
   build from the same `backend/Dockerfile` and therefore need different
   commands — then editing anything in the repository has no effect on the
   deployed worker until the dashboard value is updated too.
2. `backend/Dockerfile`'s `CMD` is the **backend's** uvicorn command. It is
   not the worker's, and it must not be repurposed: both services share the
   image.

So after changing the flags here, check the dashboard. The repository copies
below exist to document the intent and keep environments aligned; the
dashboard is what actually runs.

### The same command, in the repository

Three places define it, and they are meant to stay identical:

| Where | Applies to |
| --- | --- |
| `docker-compose.yml` → `celery-worker.command` | local development |
| `k8s/celery-worker.yaml` → `spec.template.spec.containers[0].command` | the local Kubernetes deployment |
| Railway dashboard → worker service Start Command | **production** |

## Backend service memory

Worth knowing before raising traffic: the FastAPI service legitimately loads
PyTorch and the YOLOv8n weights at startup to serve the Asset Scan endpoint,
and it does not release the memory torch allocates on first inference.

Measured locally against the real scan path (1280×720 frame):

| | cgroup memory |
| --- | --- |
| At rest, model loaded | 340.7 MB |
| After the first scan | 462.0 MB |
| Steady state over repeated scans | ~474 MB |

If the backend service is on the same 500 MB tier as the worker, that is
roughly **25 MB of headroom** — a larger frame or two concurrent scans could
plausibly cross it. It has not crashed in production, but the margin is thin
enough to be worth checking the tier rather than assuming.
