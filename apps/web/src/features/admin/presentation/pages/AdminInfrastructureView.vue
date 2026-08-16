<template>
  <main class="infrastructure-page" data-testid="admin-infrastructure-page">
    <n-page-header
      title="Infrastructure"
      subtitle="Protected operator consoles for execution and storage diagnostics."
    />

    <n-alert type="warning" title="Restricted operator access">
      These links do not grant access. Each console must be protected by TLS and an authenticated
      reverse proxy or private VPN. Use the platform for normal Dataset, Model, and Automation work.
    </n-alert>

    <n-grid cols="1 760:2" :x-gap="16" :y-gap="16">
      <n-gi v-for="consoleItem in consoles" :key="consoleItem.key">
        <n-card :title="consoleItem.name" size="small" :data-testid="`${consoleItem.key}-card`">
          <template #header-extra>
            <n-tag :type="statusTagType(consoleItem.configuration.status)" size="small" round>
              {{ statusLabel(consoleItem.configuration.status) }}
            </n-tag>
          </template>

          <n-space vertical size="large">
            <n-text depth="3">{{ consoleItem.description }}</n-text>

            <section>
              <n-text strong>Restricted operations</n-text>
              <ul class="operation-list">
                <li v-for="operation in consoleItem.operations" :key="operation">
                  {{ operation }}
                </li>
              </ul>
            </section>

            <n-alert
              v-if="consoleItem.configuration.status === 'invalid'"
              type="error"
              title="Invalid deployment configuration"
            >
              Configure a credential-free HTTPS URL. This launch action remains disabled.
            </n-alert>

            <n-text
              v-else-if="consoleItem.configuration.status === 'not-configured'"
              depth="3"
              class="configuration-note"
            >
              No protected URL is configured for this deployment.
            </n-text>

            <n-button
              v-if="consoleItem.configuration.url"
              tag="a"
              :href="consoleItem.configuration.url"
              target="_blank"
              rel="noopener noreferrer"
              type="primary"
              secondary
              :data-testid="`${consoleItem.key}-launch`"
            >
              Open protected console ↗
            </n-button>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-alert type="info" title="Deployment-owned configuration">
      Console URLs are supplied when the web container starts. They cannot be edited here and are
      never synthesized from localhost or internal container addresses.
    </n-alert>
  </main>
</template>

<script setup lang="ts">
import { getOperatorConsoleConfiguration } from "@/app/runtimeConfig";
import type { OperatorConsoleConfiguration } from "@/app/runtimeConfig";

type ConsoleStatus = OperatorConsoleConfiguration["status"];
type TagType = "default" | "success" | "error";

const configuration = getOperatorConsoleConfiguration();

const consoles = [
  {
    key: "prefect",
    name: "Prefect UI",
    description: "Execution infrastructure for flow runs, deployments, and worker health.",
    configuration: configuration.prefect,
    operations: [
      "Inspect flow-run state, logs, deployments, and work-pool health.",
      "Perform an approved retry, cancellation, or maintenance action after checking platform task state.",
      "Do not create, edit, or delete platform-managed deployments outside the release runbook.",
    ],
  },
  {
    key: "minio",
    name: "MinIO Console",
    description: "Storage infrastructure for platform artifacts, manifests, and review assets.",
    configuration: configuration.minio,
    operations: [
      "Inspect bucket, object, and version metadata during diagnostics.",
      "Verify or recover artifacts only through an approved operational runbook.",
      "Do not delete or overwrite objects, credentials, policies, or lifecycle rules from the console.",
    ],
  },
] as const;

function statusLabel(status: ConsoleStatus): string {
  if (status === "available") return "Configured";
  if (status === "invalid") return "Invalid";
  return "Not configured";
}

function statusTagType(status: ConsoleStatus): TagType {
  if (status === "available") return "success";
  if (status === "invalid") return "error";
  return "default";
}
</script>

<style scoped>
.infrastructure-page {
  display: grid;
  gap: 20px;
  max-width: 1120px;
  margin: 0 auto;
}

.operation-list {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding-left: 20px;
  color: var(--n-text-color);
}

.configuration-note {
  min-height: 34px;
}
</style>
