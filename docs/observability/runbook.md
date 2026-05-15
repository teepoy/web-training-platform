# Operational Runbook: Platform Observability

This runbook provides procedures for managing the observability stack across Docker Compose and Kubernetes environments.

## 1. Startup

### Docker Compose
The observability stack is profile-gated and must be explicitly enabled.

```bash
# Start base platform + observability (Prometheus, Grafana, Loki, Alertmanager, etc.)
docker compose -f infra/compose/docker-compose.yaml --profile observability up -d

# Enable GPU metrics (Linux/NVIDIA only)
docker compose -f infra/compose/docker-compose.yaml --profile gpu up -d dcgm-exporter

# Combined startup
docker compose -f infra/compose/docker-compose.yaml --profile observability --profile gpu up -d
```

### Kubernetes
Observability is opt-in and deployed independently of the core platform.

```bash
# Apply the self-contained observability stack
kubectl apply -k infra/k8s/observability
```

Note: If using `kube-prometheus-stack` (Prometheus Operator), refer to `infra/k8s/README.md` for `PodMonitor` application steps.

## 2. Health Checks

Verify component status using these commands. Replace `localhost` with your cluster Ingress/NodePort if applicable.

| Component | Check Command | Expected Outcome |
|-----------|---------------|------------------|
| **Prometheus** | `curl -s http://localhost:9090/-/healthy` | `Prometheus is Healthy` |
| **Prometheus Targets** | `curl -s http://localhost:9090/api/v1/targets` | `status: "success"` |
| **Loki** | `curl -s http://localhost:3100/ready` | `ready` |
| **Alertmanager** | `curl -s http://localhost:9093/api/v2/status` | JSON status object |
| **Grafana** | `curl -s http://localhost:3000/api/health` | `{"database": "ok"}` |
| **Prefect Exporter** | `curl -s http://localhost:8000/metrics` | Prometheus metrics text |
| **GPU Worker** | `curl -s http://localhost:8010/health` | `{"status": "healthy", ...}` |

## 3. Alert Silencing

Suppress alerts during maintenance windows via the Alertmanager API or UI.

### Via API (CLI)
Create a silence for all `finetune` group alerts for 2 hours:

```bash
curl -s -X POST http://localhost:9093/api/v2/silences \
  -H 'Content-Type: application/json' \
  -d '{
    "matchers": [{"name": "group", "value": "finetune", "isRegex": false}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -v+2H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "+2 hours" +%Y-%m-%dT%H:%M:%SZ)'",
    "createdBy": "ops",
    "comment": "Maintenance window"
  }'
```

List active silences:
```bash
curl -s http://localhost:9093/api/v2/silences | jq ".[] | select(.status.state == \"active\")"
```

Expire a silence by ID:
```bash
curl -s -X DELETE http://localhost:9093/api/v2/silence/<silence-id>
```

### Via UI
Open http://localhost:9093, go to the **Silences** tab, and click **New Silence**.

## 4. Dashboard Access

| Environment | Access Method | Credentials |
|-------------|---------------|-------------|
| **Compose** | http://localhost:3000 | `admin` / `admin` |
| **K8s** | `kubectl -n finetune port-forward svc/grafana 3000:3000` then http://localhost:3000 | `admin` / `admin` |

### Key Dashboards
- **GPU Runtime**: DCGM metrics, utilization, memory, and temperature.
- **Prefect Service Runtime**: Flow success rates, queue depths, and worker concurrency.
- **Runtime Logs**: Aggregated Loki logs with service/level filtering.

## 5. Troubleshooting

### DCGM Exporter not starting
- **Cause**: Host lacks NVIDIA GPU or NVIDIA Container Toolkit.
- **Symptom**: `dcgm-exporter` container fails or pod stays `Pending`.
- **Fix**: Disable the `gpu` profile in Compose or remove the DCGM DaemonSet in K8s. The platform operates normally without GPU metrics.

### Loki "No Data" or Query Timeouts
- **Cause**: High cardinality labels causing index explosion.
- **Check**: Ensure `platform_job_id` and `flow_run_id` are NOT used as Loki labels (see `docs/observability/metrics-and-logs-conventions.md`).
- **Fix**: Use LogQL content filters (`|=`) instead of label filters for high-cardinality IDs.

### Prometheus Targets Down
- **Cause**: Network partition or service name mismatch.
- **Check**: `curl` the service `/metrics` endpoint directly from inside a shell in the Prometheus container.
- **Fix**: Verify DNS names in `prometheus.yml` (Compose) or K8s Service names.

## 6. Non-GPU Behavior

On systems without NVIDIA GPUs (macOS, CPU-only Linux):
- **What works**: Everything except GPU-bound training and prediction. DSPy flows (CPU), API, and the entire observability stack (Prometheus, Loki, Grafana) remain functional.
- **What fails**: `dcgm-exporter` will not start. `gpu-worker` reports `available: false`.
- **Metrics**: GPU-specific metrics (`dcgm_*`) will be absent. Prefect and API metrics remain available.

## 7. Rollback / Migration Notes

### Reverting to Previous Worker Topology
If the split causes issues, revert to the prior deployment bundle and restore the earlier worker topology before redeploying the stack.
