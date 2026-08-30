<template>
  <main class="infrastructure-page" data-testid="admin-infrastructure-page">
    <n-page-header
      :title="t('adminInfrastructure.title')"
      :subtitle="t('adminInfrastructure.subtitle')"
    />

    <n-alert type="warning" :title="t('adminInfrastructure.restrictedTitle')">
      {{ t("adminInfrastructure.restrictedHelp") }}
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
              <n-text strong>{{ t("adminInfrastructure.restrictedOperations") }}</n-text>
              <ul class="operation-list">
                <li v-for="operation in consoleItem.operations" :key="operation">
                  {{ operation }}
                </li>
              </ul>
            </section>

            <n-alert
              v-if="consoleItem.configuration.status === 'invalid'"
              type="error"
              :title="t('adminInfrastructure.invalidTitle')"
            >
              {{ t("adminInfrastructure.invalidHelp") }}
            </n-alert>

            <n-text
              v-else-if="consoleItem.configuration.status === 'not-configured'"
              depth="3"
              class="configuration-note"
            >
              {{ t("adminInfrastructure.notConfigured") }}
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
              {{ t("adminInfrastructure.openConsole") }}
            </n-button>
          </n-space>
        </n-card>
      </n-gi>
    </n-grid>

    <n-alert type="info" :title="t('adminInfrastructure.deploymentTitle')">
      {{ t("adminInfrastructure.deploymentHelp") }}
    </n-alert>
  </main>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { OperatorConsoleConfiguration } from "@/app/runtimeConfig";
import { getOperatorConsoleConfiguration } from "@/app/runtimeConfig";

type ConsoleStatus = OperatorConsoleConfiguration["status"];
type TagType = "default" | "success" | "error";

const configuration = getOperatorConsoleConfiguration();
const { t } = useI18n();

const consoles = computed(() => [
  {
    key: "prefect",
    name: t("adminInfrastructure.prefectName"),
    description: t("adminInfrastructure.prefectDescription"),
    configuration: configuration.prefect,
    operations: [
      t("adminInfrastructure.prefectOperation1"),
      t("adminInfrastructure.prefectOperation2"),
      t("adminInfrastructure.prefectOperation3"),
    ],
  },
  {
    key: "minio",
    name: t("adminInfrastructure.minioName"),
    description: t("adminInfrastructure.minioDescription"),
    configuration: configuration.minio,
    operations: [
      t("adminInfrastructure.minioOperation1"),
      t("adminInfrastructure.minioOperation2"),
      t("adminInfrastructure.minioOperation3"),
    ],
  },
]);

function statusLabel(status: ConsoleStatus): string {
  if (status === "available") return t("adminInfrastructure.configured");
  if (status === "invalid") return t("adminInfrastructure.invalid");
  return t("adminInfrastructure.statusNotConfigured");
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
