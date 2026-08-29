# Kubernetes deployment (local, Docker Desktop)

Deploys the backend, Celery worker, PostgreSQL and Redis to Docker Desktop's
built-in single-node Kubernetes cluster. Verified working end to end on
context `docker-desktop`, node `desktop-control-plane`, Kubernetes v1.36.1.

## What is and isn't here

| Component | Manifest | Service |
| --- | --- | --- |
| PostgreSQL | `postgres.yaml` | ClusterIP + PVC (internal only) |
| Redis | `redis.yaml` | ClusterIP (internal only) |
| Backend API | `backend.yaml` | NodePort `30800` |
| Celery worker | `celery-worker.yaml` | none — it receives no inbound traffic |
| Config / secrets | `configmap.yaml`, `secret.example.yaml` | — |

**The frontend is not deployed.** It has no `Dockerfile` — it runs only via
`npm run dev` (Vite) against the API. Rather than invent a container image
for it, it is left out; run it locally and point it at the port-forwarded
backend. Adding it later means writing `frontend/Dockerfile` first.

## The one gotcha: image pull policy

The backend image is built locally and never pushed to a registry. It still
reaches the cluster, because containerd in Docker Desktop's node proxies
every pull through an internal mirror (`registry-mirror:1273`) backed by the
local Docker image store.

That works **only if the kubelet is allowed to pull**:

```yaml
imagePullPolicy: IfNotPresent   # correct
imagePullPolicy: Never          # FAILS — ErrImageNeverPull
```

`Never` means "use only images already in containerd's own store", which
bypasses the mirror entirely and fails even though `docker images` lists the
image. This is the reverse of the usual advice for local clusters, and it is
the detail that makes or breaks this deployment.

Two related dead ends, in case you are tempted:

- **`kind load docker-image` does not work here.** Docker Desktop's cluster
  is kind-based, but the node lives inside Docker Desktop's own VM and is
  not a container the Docker daemon can see. `kind get clusters` reports
  "No kind clusters found", so `kind load` has nothing to target.
- **A local in-cluster registry does not work either.** Pushing to one
  succeeds, but pulling fails: the mirror resolves `localhost:30500` in its
  own namespace, not the node's, and returns
  `500 Internal Server Error` / `short read: expected N bytes but got 0`.

## Deploy

**1. Build and tag the image**

```bash
docker compose build backend
docker tag carbonfootprintcollegeproject-backend:latest carbon-backend:v1
```

Bump the tag (`v2`, `v3`, …) whenever you rebuild, and update the `image:`
lines in `backend.yaml` and `celery-worker.yaml`. Reusing one tag with
`IfNotPresent` lets the cluster keep serving the stale copy it already has.

**2. Create the Secret** (once)

```bash
cp k8s/secret.example.yaml k8s/secret.yaml
# edit k8s/secret.yaml: set real values AND rename metadata.name to carbon-secrets
kubectl apply -f k8s/secret.yaml
```

`k8s/secret.yaml` is gitignored. The committed example is deliberately named
`carbon-secrets-example` so that applying the directory without a real
secret fails loudly (`secret "carbon-secrets" not found`) instead of
silently deploying placeholder credentials.

**3. Apply everything**

```bash
kubectl apply -f k8s/
```

**4. Wait for rollout**

```bash
kubectl rollout status deployment/postgres
kubectl rollout status deployment/backend
```

The backend takes ~30s to pull and ~30s more to start: its lifespan handler
imports torch and loads the YOLOv8n weights before serving. A `startupProbe`
allows up to 2.5 minutes for that.

Database migrations and seeding run automatically in the backend's `migrate`
init container, so a failed migration blocks startup instead of leaving a
running API on a half-migrated schema.

## Verify

```bash
kubectl get pods
```

```
NAME                             READY   STATUS    RESTARTS   AGE
backend-7994496649-msn8h         1/1     Running   0          26s
celery-worker-7fb7c6bb5d-rz8vx   1/1     Running   0          26s
postgres-84d87c4848-45fdv        1/1     Running   0          3m35s
redis-9b8db7f86-8bpvg            1/1     Running   0          3m35s
```

Check migrations actually ran:

```bash
kubectl logs deployment/backend -c migrate
```

## Reach the API

**Use `kubectl port-forward`.** The Service is a NodePort (`30800`), which is
the right type for a single-node cluster — a `LoadBalancer` would sit at
`EXTERNAL-IP <pending>` forever, since kind has no cloud controller to
satisfy it. But **Docker Desktop does not publish NodePorts to the Windows
host**: `http://localhost:30800/health` is unreachable from the host and from
the Docker daemon alike (verified). The NodePort is real and works from
inside the cluster; port-forward is how you reach it from your machine.

```bash
kubectl port-forward svc/backend 8080:8000
```

```bash
$ curl http://localhost:8080/health
{"status":"ok"}
```

The full API is available there — `http://localhost:8080/docs` for Swagger,
`http://localhost:8080/graphql` for GraphiQL.

## Teardown

```bash
kubectl delete -f k8s/
kubectl delete pvc postgres-data   # deletes the database volume too
```

`kubectl delete -f k8s/` leaves the PVC behind on purpose, so a redeploy
keeps its data. Delete it explicitly when you want a clean database.
