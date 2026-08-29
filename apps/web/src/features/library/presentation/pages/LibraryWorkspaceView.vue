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
      <ResourceFilterBar
        :keyword="searchQuery"
        :keyword-placeholder="activeTab === 'datasets' ? 'Search datasets' : 'Search collections'"
        :creator-scope="creatorScope"
        :creators="libraryCreators"
        :creators-loading="datasetCreatorsLoading || collectionCreatorsLoading"
        :active-filter-count="activeFilterCount"
        resource-label="resources"
        search-test-id="library-search"
        aria-label="Library filters"
        @update:keyword="searchQuery = $event"
        @update:creator-scope="creatorScope = $event"
        @clear="clearFilters"
      >
        <template #actions>
          <NButton
            v-if="activeTab === 'collections'"
            type="primary"
            data-testid="library-new-collection"
            @click="collectionListRef?.openCreate()"
          >
            New collection
          </NButton>
        </template>
      </ResourceFilterBar>
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
import { computed, ref, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import { useRoute, useRouter, type LocationQueryRaw } from "vue-router";
import { NButton } from "naive-ui";
import {
  useListCollectionCreatorsApiV1DatasetCollectionsCreatorsGet,
  useListDatasetCreatorsApiV1DatasetsCreatorsGet,
} from "@/generated/orval/endpoints/api";
import type { CreatorSummary } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import DatasetListView from "@/features/datasets/presentation/pages/DatasetListView.vue";
import DatasetCollectionListView from "@/features/dataset-collections/presentation/pages/DatasetCollectionListView.vue";
import { orgScopedQueryKey } from "@/shared/api";
import ResourceFilterBar from "@/shared/components/resource-filter-bar";
import { useCreatorScopeQuery } from "@/shared/composables/useCreatorScopeQuery";

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

const routeSearch = computed(() => firstQueryValue(route.query.q) ?? "");
const searchQuery = ref(routeSearch.value);
const debouncedSearchQuery = refDebounced(searchQuery, 250);
watch(routeSearch, (value) => {
  if (value !== searchQuery.value) searchQuery.value = value;
});
watch(debouncedSearchQuery, (value) => {
  const normalized = value.trim();
  if (normalized !== routeSearch.value) replaceQuery({ q: normalized || undefined });
});

const { creatorScope, creatorId } = useCreatorScopeQuery(
  () => orgStore.currentOrgId,
  () => authStore.user?.id,
);

const { data: datasetCreators, isLoading: datasetCreatorsLoading } =
  useListDatasetCreatorsApiV1DatasetsCreatorsGet({
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, ["library", "dataset-creators"]),
      ),
      enabled: computed(() => !!orgStore.currentOrgId),
    },
  });
const { data: collectionCreators, isLoading: collectionCreatorsLoading } =
  useListCollectionCreatorsApiV1DatasetCollectionsCreatorsGet({
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, ["library", "collection-creators"]),
      ),
      enabled: computed(() => !!orgStore.currentOrgId),
    },
  });

const libraryCreators = computed<CreatorSummary[]>(() => {
  const creators = new Map<string, CreatorSummary>();
  for (const creator of [...(datasetCreators.value ?? []), ...(collectionCreators.value ?? [])]) {
    creators.set(creator.id, creator);
  }
  return [...creators.values()].sort((left, right) =>
    (left.name || left.id).localeCompare(right.name || right.id),
  );
});

const activeFilterCount = computed(
  () => Number(searchQuery.value.trim().length > 0) + Number(creatorScope.value !== "all"),
);

function clearFilters(): void {
  searchQuery.value = "";
  creatorScope.value = "all";
}

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
</style>
