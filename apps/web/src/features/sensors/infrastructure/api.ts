import { req } from "@/shared/api";
import type {
  SensorDefinition,
  SensorSubscription,
  CreateSubscriptionBody,
  UpdateSubscriptionBody,
} from '../domain/models';

export function listSensors(): Promise<SensorDefinition[]> {
  return req<SensorDefinition[]>("/sensors");
}

export function listSubscriptions(sensorId: string): Promise<SensorSubscription[]> {
  return req<SensorSubscription[]>(`/sensors/${sensorId}/subscriptions`);
}

export function createSubscription(sensorId: string, body: CreateSubscriptionBody): Promise<SensorSubscription> {
  return req<SensorSubscription>(`/sensors/${sensorId}/subscriptions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSubscription(sensorId: string, subId: string, body: UpdateSubscriptionBody): Promise<SensorSubscription> {
  return req<SensorSubscription>(`/sensors/${sensorId}/subscriptions/${subId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteSubscription(sensorId: string, subId: string): Promise<void> {
  return req<void>(`/sensors/${sensorId}/subscriptions/${subId}`, {
    method: "DELETE",
  });
}
