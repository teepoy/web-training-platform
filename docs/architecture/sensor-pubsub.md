# Sensor Pub/Sub Architecture

The platform provides a sensor-based event system that follows a pub/sub model. Sensors poll or receive external data and emit events, while users create subscriptions to trigger workflows based on those events.

## Overview

Unlike traditional webhooks that push data directly to an endpoint, the sensor system decouples event generation from action execution. Sensors are engineer-authored components that run on a schedule, while subscriptions are user-defined rules that match events to platform workflows.

## Architecture

```text
+----------------------+
|  Prefect Sensor Flow |
| (polls source data)  |
+----------+-----------+
           |
           | POST /api/v1/sensors/events
           v
+----------+-----------+      +-----------------------+
|   SensorAPI Router   +----->|   SensorCheckpoint    |
+----------+-----------+      | (persistent watermark)|
           |                  +-----------------------+
           v
+----------+-----------+      +-----------------------+
|   DispatchService    +----->|  SensorSubscription   |
+----------+-----------+      | (filter + workflow)   |
           |                  +-----------+-----------+
           |                              |
           |   (matches? triggers)        |
           +------------------------------+
           |
           v
+----------+-----------+
|    Prefect Client    |
| (create_flow_run)    |
+----------------------+
```

1. **Prefect Flow**: A sensor flow runs on a cron schedule, polls for data, builds a batch of events, and POSTs them to the API.
2. **Event Ingestion**: The API receives the batch, updates the sensor's watermark (checkpoint), and hands the events to the `SensorDispatchService`.
3. **Dispatch**: The dispatch service iterates through active subscriptions for the sensor. It matches the event payload against the subscription's `filter_config`.
4. **Trigger**: If an event matches, the dispatch service triggers the requested workflow (e.g., training or prediction) via the Prefect client.

## Sensor Definition (YAML)

Sensors are defined as YAML files in `apps/api/sensors/`. These definitions are loaded into the `SensorRegistry` at startup.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Unique identifier for the sensor |
| `name` | `string` | Human-readable name |
| `description` | `string` | Explanation of what the sensor monitors |
| `cron` | `string` | Default cron schedule for the Prefect deployment |
| `filter_schema` | `object` | JSON Schema describing valid filter keys for subscriptions |
| `available_triggers`| `list[string]`| List of workflow types (e.g., `train`, `predict`) this sensor can trigger |

## Subscription Model

Users manage subscriptions via the API or frontend UI. A subscription includes:

- `filter_config`: A key-value object where every key must match the event payload for a trigger to occur. An empty object matches all events.
- `workflow_type`: The ID of the platform workflow to trigger (e.g., a specific training preset).
- `enabled`: A boolean flag to pause or resume the subscription.

## Dispatch Isolation

The `SensorDispatchService` ensures that a failure in one subscription (e.g., due to a deleted workflow or invalid config) does not abort dispatch for other subscriptions. Errors are logged per subscription, and the dispatch summary reports the total number of matched events and successful triggers.

## Checkpoint Durability

Sensors often need to track their progress (e.g., the last processed timestamp or offset) across runs. The platform provides a `sensor_checkpoints` table for this purpose. Sensors POST a `watermark` object along with their event batch, which is persisted by the API and can be retrieved by the sensor on its next run.

## Adding a New Sensor

To add a new sensor, you must:
1. Define the sensor YAML in `apps/api/sensors/`.
2. Implement the Prefect flow in `apps/api/app/flows/`.
3. Register the flow deployment in `apps/api/app/flows/serve.py`.

See the **Extension Guide** for a step-by-step walkthrough.
