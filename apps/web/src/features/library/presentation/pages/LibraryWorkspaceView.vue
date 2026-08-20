<template>
  <main class="library-workspace">
    <header class="library-header">
      <div>
        <p class="library-eyebrow">Data resources</p>
        <h1>Library</h1>
        <p class="library-description">Find and manage datasets and collections in one place.</p>
      </div>
    </header>

    <nav class="library-tabs" aria-label="Library resource types">
      <button
        type="button"
        :class="{ active: activeTab === 'datasets' }"
        data-testid="library-tab-datasets"
        @click="activeTab = 'datasets'"
      >
        Datasets
      </button>
      <button
        type="button"
        :class="{ active: activeTab === 'collections' }"
        data-testid="library-tab-collections"
        @click="activeTab = 'collections'"
      >
        Collections
      </button>
    </nav>

    <section class="library-resource-panel">
      <div class="library-query" aria-label="Library filters">
        <NInput
          :value="searchQuery"
          clearable
          :placeholder="activeTab === 'datasets' ? 'Search datasets' : 'Search collections'"
          data-testid="library-search"
          class="library-search"
          @update:value="searchQuery = $event"
        />
        <NSelect
          :value="creatorScope"
          :options="creatorOptions"
          filterable
          data-testid="library-creator"
          class="library-creator"
          @update:value="creatorScope = $event"
        />
        <NButton
          v-if="activeTab === 'collections'"
          type="primary"
          class="library-primary-action"
          data-testid="library-new-collection"
          @click="collectionListRef?.openCreate()"
        >
          New collection
        </NButton>
      </div>
      <KeepAlive>
        <component
          ref="collectionListRef"
          :is="activeListView"
          :key="activeTab"
          embedded
          :search="searchQuery"
          :creator-id="creatorId"
        />
      </KeepAlive>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";
import { NButton, NInput, NSelect } from "naive-ui";
import { useListDatasetCreatorsApiV1DatasetsCreatorsGet } from "@/generated/orval/endpoints/api";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import DatasetListView from "@/features/datasets/presentation/pages/DatasetListView.vue";
import DatasetCollectionListView from "@/features/dataset-collections/presentation/pages/DatasetCollectionListView.vue";
import { orgScopedQueryKey } from "@/shared/api";

type LibraryTab = "datasets" | "collections";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const collectionListRef = ref<{ openCreate: () => void } | null>(null);

function firstQueryValue(value: unknown): string | undefined {
  if (Array.isArray(value)) return typeof value[0] === "string" ? value[0] : undefined;
  return typeof value === "string" ? value : undefined;
}

function replaceQuery(updates: Record<string, string | undefined>): void {
  const query: LocationQueryRaw = { ...route.query };
  for (const [key, value] of Object.entries(updates)) {
    if (value === undefined || value.length === 0) {
      delete query[key];
    } else {
      query[key] = value;
    }
  }
  void router.replace({ path: "/library", query });
}

const activeTab = computed<LibraryTab>({
  get: () => (firstQueryValue(route.query.tab) === "collections" ? "collections" : "datasets"),
  set: (tab) => replaceQuery({ tab }),
});

const searchQuery = computed({
  get: () => firstQueryValue(route.query.q) ?? "",
  set: (value: string) => replaceQuery({ q: value.trim() || undefined }),
});

const creatorScope = computed({
  get: () => firstQueryValue(route.query.creator) ?? "me",
  set: (value: string) => replaceQuery({ creator: value }),
});

const creatorId = computed<string | null>(() => {
  if (creatorScope.value === "all") return null;
  if (creatorScope.value === "me") return authStore.user?.id ?? null;
  return creatorScope.value;
});

const { data: datasetCreators } = useListDatasetCreatorsApiV1DatasetsCreatorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["library", "creators"])),
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

const creatorOptions = computed(() => {
  const user = authStore.user;
  const options: Array<{ label: string; value: string }> = [
    { label: "All creators", value: "all" },
  ];
  if (user) {
    options.unshift({ label: `${user.name || user.email || user.id} (You)`, value: "me" });
  }
  for (const creator of datasetCreators.value ?? []) {
    if (creator.id === user?.id) continue;
    options.push({ label: creator.name || creator.id, value: creator.id });
  }
  const selected = creatorScope.value;
  if (selected !== "me" && selected !== "all" && !options.some(({ value }) => value === selected)) {
    options.push({ label: selected, value: selected });
  }
  return options;
});

const activeListView = computed(() =>
  activeTab.value === "collections" ? DatasetCollectionListView : DatasetListView,
);
</script>

<style scoped>
.library-workspace {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

.library-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.library-eyebrow {
  margin: 0 0 4px;
  color: #5267c9;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1.2;
}

.library-description {
  margin: 5px 0 0;
  color: var(--n-text-color-3, #6a7280);
}

.library-query {
  display: flex;
  gap: 10px;
  padding: 12px 0;
  background: var(--n-color, #fff);
  border-bottom: 1px solid var(--n-border-color, #e1e4e9);
}

.library-search {
  width: min(420px, 100%);
}

.library-creator {
  width: min(240px, 100%);
}

.library-primary-action {
  flex: none;
  margin-left: auto;
}

.library-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--n-border-color, #e1e4e9);
}

.library-tabs button {
  position: relative;
  padding: 10px 16px;
  color: var(--n-text-color-3, #6a7280);
  font: inherit;
  font-weight: 600;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.library-tabs button::after {
  position: absolute;
  right: 10px;
  bottom: -1px;
  left: 10px;
  height: 2px;
  content: "";
  background: transparent;
  border-radius: 2px;
}

.library-tabs button.active {
  color: var(--n-primary-color, #5267c9);
}

.library-tabs button.active::after {
  background: var(--n-primary-color, #5267c9);
}

.library-resource-panel {
  min-height: 0;
}

@media (max-width: 640px) {
  .library-query {
    flex-direction: column;
  }

  .library-search,
  .library-creator {
    width: 100%;
  }

  .library-primary-action {
    width: 100%;
    margin-left: 0;
  }
}
</style>
