<script setup lang="ts">
import { computed, h, ref, watch } from "vue";
import { useMutation } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import {
  NAlert,
  NButton,
  NCheckbox,
  NDataTable,
  NDatePicker,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NFormItem,
  NModal,
  NResult,
  NSelect,
  NSpace,
  NText,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import {
  previewMembershipBackfillApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdBackfillPreviewPost,
  runMembershipBackfillApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdBackfillsPost,
} from "@/generated/orval/endpoints/api";
import type {
  BackfillPreviewResponse,
  DiscoveryRunResponse,
  MembershipRuleResponse,
  SourceRecordResponse,
} from "@/generated/orval/models";
import { toUserMessage } from "@/shared/api";
import { formatDateTime, formatNumber } from "@/shared/i18n/format";
import {
  browserTimeZone,
  resolveBackfillRange,
  supportedTimeZoneOptions,
} from "../../application/backfillRange";

const props = defineProps<{
  show: boolean;
  collectionId: string;
  rule: MembershipRuleResponse | null;
}>();
const emit = defineEmits<{
  "update:show": [show: boolean];
  submitted: [run: DiscoveryRunResponse];
}>();

const { t } = useI18n();
const router = useRouter();
const message = useMessage();
const startAt = ref<number | null>(null);
const endAt = ref<number | null>(null);
const timezone = ref(browserTimeZone());
const preview = ref<BackfillPreviewResponse | null>(null);
const previewFingerprint = ref<string | null>(null);
const confirmed = ref(false);
const submittedRun = ref<DiscoveryRunResponse | null>(null);
const timezoneOptions = supportedTimeZoneOptions();
const resolvedRange = computed(() =>
  resolveBackfillRange({ startAt: startAt.value, endAt: endAt.value, timezone: timezone.value }),
);
const currentFingerprint = computed(() => JSON.stringify(resolvedRange.value));
const previewIsCurrent = computed(
  () => !!preview.value && previewFingerprint.value === currentFingerprint.value,
);
const canSubmit = computed(
  () => !!props.rule && previewIsCurrent.value && confirmed.value && !!resolvedRange.value,
);

const representativeColumns = computed<DataTableColumns<SourceRecordResponse>>(() => [
  {
    title: t("collectionDetail.backfillRecord"),
    key: "display_name",
    minWidth: 190,
  },
  {
    title: t("collectionDetail.backfillObservedAt"),
    key: "observed_at",
    minWidth: 180,
    render: (record) => formatDateTime(record.observed_at),
  },
  {
    title: t("collectionDetail.backfillAttributes"),
    key: "attributes",
    minWidth: 260,
    ellipsis: { tooltip: true },
    render: (record) => h("code", JSON.stringify(record.attributes)),
  },
]);

function reset(): void {
  const end = new Date();
  end.setSeconds(0, 0);
  const start = new Date(end);
  start.setDate(start.getDate() - 7);
  startAt.value = start.getTime();
  endAt.value = end.getTime();
  timezone.value = browserTimeZone();
  preview.value = null;
  previewFingerprint.value = null;
  confirmed.value = false;
  submittedRun.value = null;
}

watch(
  () => props.show,
  (show) => {
    if (show) reset();
  },
  { immediate: true },
);
watch([startAt, endAt, timezone], () => {
  if (previewFingerprint.value === currentFingerprint.value) return;
  preview.value = null;
  previewFingerprint.value = null;
  confirmed.value = false;
});

const previewMutation = useMutation({
  mutationFn: async () => {
    if (!props.rule || !resolvedRange.value)
      throw new Error(t("collectionDetail.backfillRangeInvalid"));
    return previewMembershipBackfillApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdBackfillPreviewPost(
      props.collectionId,
      props.rule.id,
      { ...resolvedRange.value, representative_limit: 5 },
    );
  },
  onSuccess: (result) => {
    preview.value = result;
    previewFingerprint.value = currentFingerprint.value;
    confirmed.value = false;
  },
  onError: (error) =>
    message.error(toUserMessage(error, t("collectionDetail.backfillPreviewFailed"))),
});

const runMutation = useMutation({
  mutationFn: async () => {
    if (!props.rule || !resolvedRange.value || !canSubmit.value) {
      throw new Error(t("collectionDetail.backfillConfirmationRequired"));
    }
    return runMembershipBackfillApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdBackfillsPost(
      props.collectionId,
      props.rule.id,
      resolvedRange.value,
    );
  },
  onSuccess: (run) => {
    submittedRun.value = run;
    emit("submitted", run);
    message.success(t("collectionDetail.backfillStarted"));
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.backfillFailed"))),
});

function close(): void {
  if (previewMutation.isPending.value || runMutation.isPending.value) return;
  emit("update:show", false);
}

function openAutomations(): void {
  emit("update:show", false);
  void router.push({ name: "automations" });
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="t('collectionDetail.backfillTitle', { rule: rule?.name ?? '' })"
    :style="{ width: 'min(880px, calc(100vw - 32px))' }"
    :mask-closable="!previewMutation.isPending.value && !runMutation.isPending.value"
    @update:show="(value) => (value ? undefined : close())"
  >
    <div data-testid="membership-rule-backfill-modal">
      <NResult
        v-if="submittedRun"
        status="success"
        :title="t('collectionDetail.backfillStarted')"
        :description="t('collectionDetail.backfillRunStatus', { status: submittedRun.status })"
      >
        <template #footer>
          <NSpace justify="center">
            <NButton @click="close">{{ t("common.close") }}</NButton>
            <NButton type="primary" @click="openAutomations">
              {{ t("collectionDetail.viewAutomations") }}
            </NButton>
          </NSpace>
        </template>
      </NResult>
      <template v-else>
        <NAlert type="info" :show-icon="false" class="backfill-intro">
          {{ t("collectionDetail.backfillIntro") }}
        </NAlert>
        <div class="backfill-range-grid">
          <NFormItem :label="t('collectionDetail.backfillStart')" required>
            <NDatePicker
              v-model:value="startAt"
              data-testid="backfill-start"
              type="datetime"
              clearable
            />
          </NFormItem>
          <NFormItem :label="t('collectionDetail.backfillEnd')" required>
            <NDatePicker
              v-model:value="endAt"
              data-testid="backfill-end"
              type="datetime"
              clearable
            />
          </NFormItem>
          <NFormItem
            :label="t('collectionDetail.backfillTimezone')"
            required
            :validation-status="timezone && !resolvedRange ? 'error' : undefined"
          >
            <NSelect
              v-model:value="timezone"
              data-testid="backfill-timezone"
              filterable
              tag
              :options="timezoneOptions"
            />
          </NFormItem>
        </div>
        <NAlert v-if="!resolvedRange" type="error" :show-icon="false">
          {{ t("collectionDetail.backfillRangeInvalid") }}
        </NAlert>

        <template v-if="previewIsCurrent && preview">
          <NDescriptions bordered size="small" :column="2" class="backfill-summary">
            <NDescriptionsItem :label="t('collectionDetail.backfillMatched')">
              <strong data-testid="backfill-matched-count">
                {{ formatNumber(preview.matched_count) }}
              </strong>
            </NDescriptionsItem>
            <NDescriptionsItem :label="t('collectionDetail.backfillAsOf')">
              {{ formatDateTime(preview.as_of_utc) }}
            </NDescriptionsItem>
          </NDescriptions>
          <NText strong>{{ t("collectionDetail.backfillRepresentative") }}</NText>
          <NDataTable
            v-if="preview.representative_records.length > 0"
            size="small"
            :columns="representativeColumns"
            :data="preview.representative_records"
            :row-key="(record: SourceRecordResponse) => record.record_key"
            :scroll-x="680"
          />
          <NEmpty v-else :description="t('collectionDetail.backfillNoRepresentative')" />
          <NAlert type="warning" :show-icon="false" class="backfill-confirmation">
            <NCheckbox v-model:checked="confirmed" data-testid="backfill-confirm-all">
              {{
                t(
                  "collectionDetail.backfillConfirmAll",
                  { count: preview.matched_count },
                  preview.matched_count,
                )
              }}
            </NCheckbox>
          </NAlert>
        </template>
      </template>
    </div>

    <template v-if="!submittedRun" #footer>
      <NSpace justify="space-between">
        <NButton @click="close">{{ t("common.cancel") }}</NButton>
        <NSpace>
          <NButton
            :disabled="!resolvedRange"
            :loading="previewMutation.isPending.value"
            data-testid="backfill-preview"
            @click="previewMutation.mutate()"
          >
            {{ t("collectionDetail.backfillPreview") }}
          </NButton>
          <NButton
            type="primary"
            :disabled="!canSubmit"
            :loading="runMutation.isPending.value"
            data-testid="backfill-submit"
            @click="runMutation.mutate()"
          >
            {{ t("collectionDetail.backfillImportAll") }}
          </NButton>
        </NSpace>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped>
.backfill-intro,
.backfill-summary,
.backfill-confirmation {
  margin-bottom: 16px;
}

.backfill-range-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.backfill-confirmation {
  margin-top: 16px;
}

@media (max-width: 760px) {
  .backfill-range-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
