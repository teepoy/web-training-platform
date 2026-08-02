<script setup lang="ts">
import { computed, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NDivider,
  NInputNumber,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSwitch,
  NTag,
  useMessage,
} from "naive-ui";

type GroupRuleKind = "quota" | "rate";
type QuotaUnit = "count" | "ratio";

interface PopulationGroup {
  key: string;
  label: string;
  count: number;
  filterRate: number;
  color: string;
}

interface PreviewGroup extends PopulationGroup {
  eligible: number;
  selected: number;
}

interface RuleCatalogItem {
  id: "global" | "conditional" | "quota" | "rate" | "total";
  order: string;
  title: string;
  subtitle: string;
  description: string;
}

const groups: PopulationGroup[] = [
  {
    key: "scratch",
    label: "Scratch",
    count: 1280,
    filterRate: 0.72,
    color: "#2f7658",
  },
  {
    key: "particle",
    label: "Particle",
    count: 760,
    filterRate: 0.64,
    color: "#5b9c7c",
  },
  {
    key: "residue",
    label: "Residue",
    count: 310,
    filterRate: 0.58,
    color: "#d49a51",
  },
  {
    key: "unknown",
    label: "Unknown",
    count: 150,
    filterRate: 0.46,
    color: "#87928c",
  },
];

const catalog: RuleCatalogItem[] = [
  {
    id: "global",
    order: "01",
    title: "Global filter",
    subtitle: "全局筛选",
    description: "先收窄所有后续规则的候选池。",
  },
  {
    id: "conditional",
    order: "02",
    title: "Conditional limit",
    subtitle: "条件总量限制",
    description: "只限制命中条件的子集，其他样本保留。",
  },
  {
    id: "quota",
    order: "03A",
    title: "Group quota",
    subtitle: "按组挑选总量 / 构成比例",
    description: "控制最终样本中每个组的数量或占比。",
  },
  {
    id: "rate",
    order: "03B",
    title: "Group sampling rate",
    subtitle: "分组挑选比例",
    description: "按每个组自身候选量独立抽取一定比例。",
  },
  {
    id: "total",
    order: "04",
    title: "Total limit",
    subtitle: "总量限制",
    description: "最终结果上限；不足时不隐式补样。",
  },
];

const message = useMessage();
const globalEnabled = ref(true);
const confidenceThreshold = ref(0.65);
const conditionalEnabled = ref(true);
const conditionalGroup = ref("unknown");
const conditionalLimit = ref(45);
const groupEnabled = ref(true);
const groupRuleKind = ref<GroupRuleKind>("quota");
const quotaUnit = ref<QuotaUnit>("ratio");
const totalEnabled = ref(true);
const totalLimit = ref(200);
const seed = ref(20260731);
const runVersion = ref(1);
const groupCounts = ref<Record<string, number>>({
  scratch: 80,
  particle: 60,
  residue: 40,
  unknown: 20,
});
const groupRatios = ref<Record<string, number>>({
  scratch: 40,
  particle: 30,
  residue: 20,
  unknown: 10,
});
const groupRates = ref<Record<string, number>>({
  scratch: 10,
  particle: 15,
  residue: 25,
  unknown: 40,
});

const baseTotal = computed(() => groups.reduce((sum, group) => sum + group.count, 0));
const afterGlobal = computed(() =>
  groups.map((group) => {
    const threshold = Math.min(Math.max(confidenceThreshold.value ?? 0, 0), 1);
    const adjustedRate = Math.min(Math.max(group.filterRate + (0.65 - threshold) * 0.8, 0), 1);
    return {
      ...group,
      eligible: globalEnabled.value ? Math.floor(group.count * adjustedRate) : group.count,
    };
  }),
);
const globalTotal = computed(() =>
  afterGlobal.value.reduce((sum, group) => sum + group.eligible, 0),
);
const afterConditional = computed(() =>
  afterGlobal.value.map((group) => ({
    ...group,
    eligible:
      conditionalEnabled.value && group.key === conditionalGroup.value
        ? Math.min(group.eligible, conditionalLimit.value ?? 0)
        : group.eligible,
  })),
);
const conditionalTotal = computed(() =>
  afterConditional.value.reduce((sum, group) => sum + group.eligible, 0),
);
const ratioTotal = computed(() =>
  groups.reduce((sum, group) => sum + (groupRatios.value[group.key] ?? 0), 0),
);
const totalLimitValue = computed(() =>
  totalEnabled.value ? Math.max(totalLimit.value ?? 0, 0) : conditionalTotal.value,
);

function largestRemainder(values: number[], total: number): number[] {
  const ideals = values.map((value) => (value / 100) * total);
  const result = ideals.map(Math.floor);
  let remaining = total - result.reduce((sum, value) => sum + value, 0);
  const ranked = ideals
    .map((ideal, index) => ({ index, remainder: ideal - Math.floor(ideal) }))
    .sort((left, right) => right.remainder - left.remainder || left.index - right.index);
  for (const { index } of ranked) {
    if (remaining === 0) break;
    result[index] = (result[index] ?? 0) + 1;
    remaining -= 1;
  }
  return result;
}

const groupStage = computed<PreviewGroup[]>(() => {
  const eligible = afterConditional.value;
  if (!groupEnabled.value) {
    return eligible.map((group) => ({ ...group, selected: group.eligible }));
  }
  if (groupRuleKind.value === "rate") {
    return eligible.map((group) => ({
      ...group,
      selected: Math.min(
        group.eligible,
        Math.floor((group.eligible * (groupRates.value[group.key] ?? 0)) / 100 + 0.5),
      ),
    }));
  }
  const planned =
    quotaUnit.value === "count"
      ? groups.map((group) => groupCounts.value[group.key] ?? 0)
      : largestRemainder(
          groups.map((group) => groupRatios.value[group.key] ?? 0),
          totalLimitValue.value,
        );
  return eligible.map((group, index) => ({
    ...group,
    selected: Math.min(group.eligible, planned[index] ?? 0),
  }));
});

const groupTotal = computed(() => groupStage.value.reduce((sum, group) => sum + group.selected, 0));
const finalTotal = computed(() => Math.min(groupTotal.value, totalLimitValue.value));
const ratioValid = computed(
  () =>
    groupRuleKind.value !== "quota" ||
    quotaUnit.value !== "ratio" ||
    (totalEnabled.value && ratioTotal.value === 100),
);
const hasConfigurationError = computed(
  () =>
    !ratioValid.value ||
    (conditionalEnabled.value && (conditionalLimit.value ?? -1) < 0) ||
    (totalEnabled.value && (totalLimit.value ?? -1) < 0),
);

const finalGroups = computed<PreviewGroup[]>(() => {
  if (groupTotal.value <= finalTotal.value) return groupStage.value;
  const values = groupStage.value.map(
    (group) => (group.selected / Math.max(groupTotal.value, 1)) * 100,
  );
  const capped = largestRemainder(values, finalTotal.value);
  return groupStage.value.map((group, index) => ({
    ...group,
    selected: Math.min(group.selected, capped[index] ?? 0),
  }));
});
const maxSelected = computed(() =>
  Math.max(...finalGroups.value.map((group) => group.selected), 1),
);

const activeRuleCount = computed(
  () =>
    Number(globalEnabled.value) +
    Number(conditionalEnabled.value) +
    Number(groupEnabled.value) +
    Number(totalEnabled.value),
);

const stageCounts = computed(() => [
  { label: "Input", value: baseTotal.value },
  { label: "Global", value: globalTotal.value },
  { label: "Conditional", value: conditionalTotal.value },
  { label: "Group", value: groupTotal.value },
  { label: "Final", value: finalTotal.value },
]);

const rulePayload = computed(() => {
  const rules: Array<Record<string, unknown>> = [];
  if (globalEnabled.value) {
    rules.push({
      type: "global_filter",
      where: {
        match: "all",
        conditions: [
          {
            field: "metadata.confidence",
            operator: "gte",
            value: confidenceThreshold.value,
          },
        ],
      },
    });
  }
  if (conditionalEnabled.value) {
    rules.push({
      type: "conditional_limit",
      where: {
        match: "all",
        conditions: [
          {
            field: "metadata.defect_code",
            operator: "eq",
            value: conditionalGroup.value,
          },
        ],
      },
      limit: conditionalLimit.value,
    });
  }
  if (groupEnabled.value && groupRuleKind.value === "quota") {
    rules.push({
      type: "group_quota",
      group_by: ["metadata.defect_code"],
      unit: quotaUnit.value,
      targets: groups.map((group) => ({
        group: [group.key],
        amount:
          quotaUnit.value === "count"
            ? groupCounts.value[group.key]
            : (groupRatios.value[group.key] ?? 0) / 100,
      })),
      shortfall: "take_available",
      unlisted: "exclude",
    });
  }
  if (groupEnabled.value && groupRuleKind.value === "rate") {
    rules.push({
      type: "group_sampling_rate",
      group_by: ["metadata.defect_code"],
      rates: groups.map((group) => ({
        group: [group.key],
        ratio: (groupRates.value[group.key] ?? 0) / 100,
      })),
      rounding: "nearest",
      unlisted: "exclude",
    });
  }
  if (totalEnabled.value) {
    rules.push({ type: "total_limit", limit: totalLimit.value });
  }
  return { seed: seed.value, rules };
});

function ruleIsActive(id: RuleCatalogItem["id"]): boolean {
  if (id === "global") return globalEnabled.value;
  if (id === "conditional") return conditionalEnabled.value;
  if (id === "total") return totalEnabled.value;
  return groupEnabled.value && groupRuleKind.value === id;
}

function activateRule(id: RuleCatalogItem["id"]): void {
  if (id === "global") globalEnabled.value = !globalEnabled.value;
  else if (id === "conditional") conditionalEnabled.value = !conditionalEnabled.value;
  else if (id === "total") totalEnabled.value = !totalEnabled.value;
  else {
    groupEnabled.value = true;
    groupRuleKind.value = id;
  }
}

function runPreview(): void {
  if (hasConfigurationError.value) {
    message.error("Resolve the rule configuration errors before previewing.");
    return;
  }
  runVersion.value += 1;
  message.success(
    `${activeRuleCount.value} rules resolved ${finalTotal.value} random samples with seed ${seed.value}.`,
  );
}
</script>

<template>
  <main class="sampling-builder">
    <header class="page-header">
      <div>
        <div class="eyebrow">SAMPLING LAB · RULE PIPELINE</div>
        <h1>Sampling rule builder</h1>
        <p>Rules narrow and shape the candidate pool; random sampling still chooses the rows.</p>
      </div>
      <NButton type="primary" size="large" :disabled="hasConfigurationError" @click="runPreview">
        Run preview
      </NButton>
    </header>

    <section class="pipeline-strip">
      <template v-for="(stage, index) in stageCounts" :key="stage.label">
        <div class="pipeline-stage" :class="{ final: index === stageCounts.length - 1 }">
          <small>{{ index === 0 ? "SOURCE" : `0${index}` }}</small>
          <strong>{{ stage.value.toLocaleString() }}</strong>
          <span>{{ stage.label }}</span>
        </div>
        <span v-if="index < stageCounts.length - 1" class="pipeline-arrow">→</span>
      </template>
      <div class="random-badge">
        <span>RANDOM</span>
        <strong>seed {{ seed }}</strong>
      </div>
    </section>

    <div class="builder-grid">
      <aside class="catalog-column">
        <div class="section-label">RULE TYPES</div>
        <button
          v-for="item in catalog"
          :key="item.id"
          class="catalog-item"
          :class="{ active: ruleIsActive(item.id) }"
          type="button"
          @click="activateRule(item.id)"
        >
          <span class="catalog-order">{{ item.order }}</span>
          <span class="catalog-copy">
            <strong>{{ item.title }}</strong>
            <small>{{ item.subtitle }}</small>
            <em>{{ item.description }}</em>
          </span>
          <span class="catalog-state">{{ ruleIsActive(item.id) ? "ON" : "OFF" }}</span>
        </button>
        <NAlert type="info" :show-icon="false" class="catalog-note">
          03A 与 03B 是互斥的分组策略；其他规则按编号固定执行。
        </NAlert>
      </aside>

      <section class="editor-column">
        <div class="section-heading">
          <div>
            <div class="section-label">ACTIVE PIPELINE</div>
            <h2>Rule configuration</h2>
          </div>
          <NTag round type="success">{{ activeRuleCount }} active</NTag>
        </div>

        <NCard v-if="globalEnabled" :bordered="false" class="rule-card">
          <template #header>
            <div class="rule-title">
              <span class="rule-index">01</span>
              <div><strong>Global filter</strong><small>全局筛选</small></div>
            </div>
          </template>
          <template #header-extra><NSwitch v-model:value="globalEnabled" /></template>
          <div class="condition-row">
            <NSelect
              value="metadata.confidence"
              :options="[{ label: 'Confidence', value: 'metadata.confidence' }]"
            />
            <NSelect value="gte" :options="[{ label: '≥', value: 'gte' }]" />
            <NInputNumber v-model:value="confidenceThreshold" :min="0" :max="1" :step="0.05" />
          </div>
          <div class="rule-foot">
            <span>作用于所有后续规则</span>
            <strong>{{ baseTotal.toLocaleString() }} → {{ globalTotal.toLocaleString() }}</strong>
          </div>
        </NCard>

        <NCard v-if="conditionalEnabled" :bordered="false" class="rule-card">
          <template #header>
            <div class="rule-title">
              <span class="rule-index">02</span>
              <div><strong>Conditional limit</strong><small>条件总量限制</small></div>
            </div>
          </template>
          <template #header-extra><NSwitch v-model:value="conditionalEnabled" /></template>
          <div class="condition-row">
            <NSelect
              value="metadata.defect_code"
              :options="[{ label: 'Defect code', value: 'metadata.defect_code' }]"
            />
            <NSelect value="eq" :options="[{ label: '=', value: 'eq' }]" />
            <NSelect
              v-model:value="conditionalGroup"
              :options="groups.map((group) => ({ label: group.label, value: group.key }))"
            />
            <NInputNumber v-model:value="conditionalLimit" :min="0" :precision="0">
              <template #suffix>max</template>
            </NInputNumber>
          </div>
          <div class="rule-foot">
            <span>只收紧命中组，未命中样本保留</span>
            <strong
              >{{ globalTotal.toLocaleString() }} → {{ conditionalTotal.toLocaleString() }}</strong
            >
          </div>
        </NCard>

        <NCard v-if="groupEnabled" :bordered="false" class="rule-card group-card">
          <template #header>
            <div class="rule-title">
              <span class="rule-index">03</span>
              <div>
                <strong>{{
                  groupRuleKind === "quota" ? "Group quota" : "Group sampling rate"
                }}</strong>
                <small>{{
                  groupRuleKind === "quota" ? "按组挑选总量 / 构成比例" : "分组挑选比例"
                }}</small>
              </div>
            </div>
          </template>
          <template #header-extra><NSwitch v-model:value="groupEnabled" /></template>

          <div class="group-toolbar">
            <NRadioGroup v-model:value="groupRuleKind">
              <NRadioButton value="quota">Group quota</NRadioButton>
              <NRadioButton value="rate">Group rate</NRadioButton>
            </NRadioGroup>
            <NRadioGroup v-if="groupRuleKind === 'quota'" v-model:value="quotaUnit">
              <NRadioButton value="count">Count</NRadioButton>
              <NRadioButton value="ratio">Final ratio</NRadioButton>
            </NRadioGroup>
          </div>

          <NAlert
            v-if="groupRuleKind === 'quota' && quotaUnit === 'ratio' && !totalEnabled"
            type="error"
            :show-icon="false"
          >
            Final ratio requires a total limit to resolve absolute quotas.
          </NAlert>
          <NAlert
            v-else-if="groupRuleKind === 'quota' && quotaUnit === 'ratio' && ratioTotal !== 100"
            type="error"
            :show-icon="false"
          >
            Final composition ratios must total 100%; current total is {{ ratioTotal }}%.
          </NAlert>

          <div class="group-table">
            <div class="group-table-head">
              <span>Group</span><span>Eligible</span><span>Rule value</span><span>Planned</span>
            </div>
            <div v-for="group in groupStage" :key="group.key" class="group-table-row">
              <span class="group-name"
                ><i :style="{ background: group.color }" />{{ group.label }}</span
              >
              <span>{{ group.eligible.toLocaleString() }}</span>
              <NInputNumber
                v-if="groupRuleKind === 'quota' && quotaUnit === 'count'"
                v-model:value="groupCounts[group.key]"
                :min="0"
                :precision="0"
              />
              <NInputNumber
                v-else-if="groupRuleKind === 'quota'"
                v-model:value="groupRatios[group.key]"
                :min="0"
                :max="100"
                :precision="0"
              >
                <template #suffix>% final</template>
              </NInputNumber>
              <NInputNumber
                v-else
                v-model:value="groupRates[group.key]"
                :min="0"
                :max="100"
                :precision="0"
              >
                <template #suffix>% group</template>
              </NInputNumber>
              <strong>{{ group.selected }}</strong>
            </div>
          </div>
          <div class="rule-foot">
            <span>{{
              groupRuleKind === "quota"
                ? "控制最终构成；组不足时 take_available"
                : "每个组按自身候选量计算"
            }}</span>
            <strong
              >{{ conditionalTotal.toLocaleString() }} → {{ groupTotal.toLocaleString() }}</strong
            >
          </div>
        </NCard>

        <NCard v-if="totalEnabled" :bordered="false" class="rule-card">
          <template #header>
            <div class="rule-title">
              <span class="rule-index">04</span>
              <div><strong>Total limit</strong><small>总量限制</small></div>
            </div>
          </template>
          <template #header-extra><NSwitch v-model:value="totalEnabled" /></template>
          <div class="total-limit-row">
            <div>
              <span>Maximum final samples</span>
              <small>这是上限，不会为了凑数隐式补样。</small>
            </div>
            <NInputNumber v-model:value="totalLimit" :min="0" :precision="0" />
          </div>
          <div class="rule-foot">
            <span>最终随机收口</span>
            <strong>{{ groupTotal.toLocaleString() }} → {{ finalTotal.toLocaleString() }}</strong>
          </div>
        </NCard>

        <NCard :bordered="false" class="seed-card">
          <div class="seed-row">
            <div>
              <strong>Random draw</strong>
              <small>规则只决定候选与配额；seed 决定具体选中哪些行。</small>
            </div>
            <NInputNumber v-model:value="seed" :precision="0" />
          </div>
        </NCard>
      </section>

      <aside class="preview-column">
        <NCard :bordered="false" class="preview-card">
          <template #header>
            <div>
              <strong>Final distribution</strong>
              <small>after all active rules</small>
            </div>
          </template>
          <div class="final-total">
            <strong>{{ finalTotal }}</strong>
            <span>random samples</span>
          </div>
          <NDivider />
          <div v-for="group in finalGroups" :key="group.key" class="distribution-row">
            <div>
              <span class="group-name"
                ><i :style="{ background: group.color }" />{{ group.label }}</span
              >
              <small>{{ group.selected }} / {{ group.eligible }}</small>
            </div>
            <div class="distribution-track">
              <span
                :style="{
                  width: `${(group.selected / maxSelected) * 100}%`,
                  background: group.color,
                }"
              />
            </div>
            <strong>{{ ((group.selected / Math.max(finalTotal, 1)) * 100).toFixed(0) }}%</strong>
          </div>
        </NCard>

        <NCard title="Rule audit" :bordered="false" class="preview-card audit-card">
          <div v-for="(stage, index) in stageCounts.slice(1)" :key="stage.label" class="audit-row">
            <span>0{{ index + 1 }}</span>
            <div>
              <strong>{{ stage.label }}</strong
              ><small>{{ stage.value }} remain</small>
            </div>
            <em>{{ index === stageCounts.length - 2 ? "FINAL" : "PASS" }}</em>
          </div>
        </NCard>

        <NCard title="Library payload" :bordered="false" class="preview-card payload-card">
          <pre>{{ JSON.stringify(rulePayload, null, 2) }}</pre>
        </NCard>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.sampling-builder {
  min-height: 100%;
  padding: 28px;
  color: #18251f;
  background:
    radial-gradient(circle at 92% 2%, rgba(190, 218, 199, 0.52), transparent 28rem), #f3f6f2;
}

.page-header,
.section-heading,
.rule-title,
.rule-foot,
.total-limit-row,
.seed-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-header,
.pipeline-strip,
.builder-grid {
  max-width: 1540px;
  margin-right: auto;
  margin-left: auto;
}

.page-header {
  margin-bottom: 20px;
}

.eyebrow,
.section-label {
  color: #397457;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

h1 {
  margin: 5px 0 0;
  font-size: clamp(27px, 3vw, 38px);
  line-height: 1.12;
  letter-spacing: -0.035em;
}

.page-header p {
  margin: 8px 0 0;
  color: #64726b;
}

.pipeline-strip {
  display: flex;
  align-items: stretch;
  gap: 11px;
  padding: 13px;
  margin-bottom: 22px;
  overflow: hidden;
  background: #dfece2;
  border: 1px solid #d3e1d6;
  border-radius: 17px;
}

.pipeline-stage {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 9px;
  align-items: center;
  min-width: 112px;
  padding: 8px 10px;
}

.pipeline-stage small {
  grid-row: 1 / 3;
  color: #4c7b62;
  font-size: 9px;
  font-weight: 800;
}

.pipeline-stage strong {
  font-size: 17px;
  line-height: 1;
}

.pipeline-stage span {
  color: #718078;
  font-size: 10px;
}

.pipeline-stage.final {
  background: rgba(255, 255, 255, 0.68);
  border-radius: 11px;
}

.pipeline-arrow {
  align-self: center;
  color: #8ba093;
}

.random-badge {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 8px 15px;
  margin-left: auto;
  color: white;
  background: #326e52;
  border-radius: 11px;
}

.random-badge span {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.random-badge strong {
  margin-top: 2px;
  font-size: 11px;
}

.builder-grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.6fr) minmax(560px, 1.55fr) minmax(270px, 0.8fr);
  gap: 18px;
  align-items: start;
}

.catalog-column,
.editor-column,
.preview-column {
  min-width: 0;
}

.catalog-column > .section-label {
  display: block;
  margin: 0 0 10px 4px;
}

.catalog-item {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  gap: 10px;
  width: 100%;
  padding: 14px 12px;
  margin-bottom: 9px;
  color: inherit;
  text-align: left;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid #dfe5df;
  border-radius: 13px;
  cursor: pointer;
  transition:
    transform 150ms ease,
    border-color 150ms ease,
    background 150ms ease;
}

.catalog-item:hover {
  transform: translateY(-1px);
  border-color: #a9c8b4;
}

.catalog-item.active {
  background: white;
  border-color: #78a88c;
  box-shadow: 0 8px 26px rgba(40, 87, 62, 0.08);
}

.catalog-order {
  color: #5c8b70;
  font-size: 10px;
  font-weight: 800;
}

.catalog-copy,
.catalog-copy strong,
.catalog-copy small,
.catalog-copy em {
  display: block;
}

.catalog-copy strong {
  font-size: 13px;
}

.catalog-copy small {
  margin-top: 2px;
  color: #557264;
  font-size: 10px;
}

.catalog-copy em {
  margin-top: 6px;
  color: #7a867f;
  font-size: 10px;
  font-style: normal;
  line-height: 1.4;
}

.catalog-state {
  color: #8a958f;
  font-size: 9px;
  font-weight: 800;
}

.catalog-item.active .catalog-state {
  color: #2f7658;
}

.catalog-note {
  margin-top: 14px;
  font-size: 11px;
}

.section-heading {
  min-height: 44px;
  margin-bottom: 10px;
}

.section-heading h2 {
  margin: 3px 0 0;
  font-size: 20px;
}

.rule-card,
.seed-card,
.preview-card {
  margin-bottom: 14px;
  overflow: hidden;
  border: 1px solid #dfe5df;
  border-radius: 15px;
  box-shadow: 0 9px 30px rgba(31, 52, 42, 0.045);
}

.rule-card :deep(.n-card-header) {
  padding-bottom: 14px;
}

.rule-title {
  justify-content: flex-start;
  gap: 10px;
}

.rule-index {
  display: grid;
  width: 31px;
  height: 31px;
  color: #347052;
  font-size: 10px;
  font-weight: 800;
  background: #e3efe6;
  border-radius: 9px;
  place-items: center;
}

.rule-title strong,
.rule-title small,
.preview-card :deep(.n-card-header__main) strong,
.preview-card :deep(.n-card-header__main) small {
  display: block;
}

.rule-title strong {
  font-size: 14px;
}

.rule-title small {
  margin-top: 1px;
  color: #728078;
  font-size: 10px;
}

.condition-row {
  display: grid;
  grid-template-columns: minmax(140px, 1.4fr) minmax(70px, 0.45fr) minmax(110px, 0.9fr) minmax(
      100px,
      0.75fr
    );
  gap: 9px;
}

.condition-row > :last-child:nth-child(3) {
  grid-column: 3 / 5;
}

.rule-foot {
  padding-top: 12px;
  margin-top: 13px;
  color: #7a867f;
  font-size: 10px;
  border-top: 1px solid #eef1ee;
}

.rule-foot strong {
  color: #375f4a;
  font-size: 11px;
}

.group-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.group-table {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid #e8ece8;
  border-radius: 11px;
}

.group-table-head,
.group-table-row {
  display: grid;
  grid-template-columns: minmax(110px, 1fr) 75px minmax(145px, 1.1fr) 55px;
  gap: 10px;
  align-items: center;
  padding: 8px 11px;
}

.group-table-head {
  color: #879189;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: #f5f7f4;
}

.group-table-row {
  min-height: 47px;
  font-size: 11px;
  border-top: 1px solid #eef1ee;
}

.group-name {
  display: flex;
  align-items: center;
  gap: 7px;
}

.group-name i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.total-limit-row > div,
.seed-row > div {
  display: flex;
  flex-direction: column;
}

.total-limit-row span,
.seed-row strong {
  font-size: 12px;
  font-weight: 700;
}

.total-limit-row small,
.seed-row small {
  margin-top: 3px;
  color: #78847d;
  font-size: 10px;
}

.total-limit-row :deep(.n-input-number),
.seed-row :deep(.n-input-number) {
  width: 155px;
}

.final-total {
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: #2f6d4f;
}

.final-total strong {
  font-size: 42px;
  line-height: 1;
  letter-spacing: -0.05em;
}

.final-total span {
  color: #77837c;
  font-size: 11px;
}

.preview-card :deep(.n-card-header__main) small {
  margin-top: 2px;
  color: #7d8982;
  font-size: 10px;
  font-weight: 400;
}

.distribution-row {
  display: grid;
  grid-template-columns: 88px 1fr 32px;
  gap: 8px;
  align-items: center;
  margin-bottom: 15px;
}

.distribution-row > div:first-child small {
  display: block;
  margin: 3px 0 0 15px;
  color: #8a948e;
  font-size: 9px;
}

.distribution-row .group-name {
  font-size: 10px;
}

.distribution-track {
  height: 7px;
  overflow: hidden;
  background: #edf1ed;
  border-radius: 8px;
}

.distribution-track span {
  display: block;
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
}

.distribution-row > strong {
  font-size: 10px;
}

.audit-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 9px;
  align-items: center;
  min-height: 43px;
  border-bottom: 1px solid #eef1ee;
}

.audit-row:last-child {
  border-bottom: 0;
}

.audit-row > span {
  color: #5f8d73;
  font-size: 9px;
  font-weight: 800;
}

.audit-row strong,
.audit-row small {
  display: block;
}

.audit-row strong {
  font-size: 10px;
}

.audit-row small {
  color: #89938e;
  font-size: 9px;
}

.audit-row em {
  color: #4d8063;
  font-size: 8px;
  font-style: normal;
  font-weight: 800;
}

.payload-card pre {
  max-height: 360px;
  padding: 12px;
  margin: 0;
  overflow: auto;
  color: #385144;
  font-size: 10px;
  line-height: 1.5;
  white-space: pre-wrap;
  background: #f4f7f4;
  border-radius: 9px;
}

@media (max-width: 1500px) {
  .builder-grid {
    grid-template-columns: minmax(210px, 0.55fr) minmax(520px, 1.45fr);
  }

  .preview-column {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }
}

@media (max-width: 1050px) {
  .builder-grid {
    grid-template-columns: 1fr;
  }

  .preview-column {
    grid-column: auto;
    grid-template-columns: 1fr;
  }

  .catalog-column {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }

  .catalog-column > .section-label,
  .catalog-note {
    grid-column: 1 / -1;
  }

  .catalog-item {
    margin-bottom: 0;
  }
}

@media (max-width: 900px) {
  .sampling-builder {
    padding: 18px;
  }

  .page-header {
    align-items: flex-start;
    gap: 12px;
  }

  .pipeline-strip {
    flex-wrap: wrap;
  }

  .pipeline-arrow {
    display: none;
  }

  .random-badge {
    margin-left: 0;
  }

  .catalog-column {
    grid-template-columns: 1fr;
  }

  .catalog-column > .section-label,
  .catalog-note {
    grid-column: auto;
  }

  .condition-row,
  .group-table-head,
  .group-table-row {
    grid-template-columns: 1fr 1fr;
  }

  .condition-row > :last-child:nth-child(3) {
    grid-column: auto;
  }

  .group-toolbar,
  .total-limit-row,
  .seed-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
