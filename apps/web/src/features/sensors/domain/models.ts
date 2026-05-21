export interface SensorDefinition {
  id: string;
  name: string;
  description: string;
  cron: string;
  filter_schema: Record<string, unknown>;
  available_triggers: string[];
}

export interface SensorSubscription {
  id: string;
  sensor_id: string;
  workflow_type: string;
  filter_config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateSubscriptionBody {
  workflow_type: string;
  filter_config?: Record<string, unknown>;
  enabled?: boolean;
}

export interface UpdateSubscriptionBody {
  filter_config?: Record<string, unknown>;
  enabled?: boolean;
}
