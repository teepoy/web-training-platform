<script setup lang="ts">
import { computed, ref } from "vue";
import { marked, type Tokens } from "marked";
import { useThemeVars } from "naive-ui";
import { FullScreenLayout } from "@/shared/components/full-screen-layout";
import mdRaw from "../../handbook/sc-guide.md?raw";

interface TocItem {
  id: string;
  text: string;
  depth: number;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

const tokens = marked.lexer(mdRaw);

const tocItems: TocItem[] = [];
for (const token of tokens) {
  if (token.type === "heading" && token.depth <= 3) {
    tocItems.push({
      id: slugify(token.text),
      text: token.text,
      depth: token.depth,
    });
  }
}

const headingIdMap = new Map<string, string>();
for (const item of tocItems) {
  headingIdMap.set(item.text, item.id);
}

marked.use({
  renderer: {
    heading({ text, depth }: Tokens.Heading): string {
      const id = slugify(text);
      headingIdMap.set(text, id);
      const tag = `h${depth}`;
      return `<${tag} id="${id}">${text}</${tag}>`;
    },
  },
});

const htmlContent = computed(() => marked.parse(mdRaw) as string);

const activeId = ref<string>("");

function scrollToHeading(id: string) {
  activeId.value = id;
  const el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

const themeVars = useThemeVars();

const containerStyle = computed(() => ({
  "--cv-bg": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text": themeVars.value.textColor1,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-border": themeVars.value.borderColor,
  "--cv-primary": themeVars.value.primaryColor,
  "--cv-primary-hover": themeVars.value.primaryColorHover,
  "--cv-hover": themeVars.value.hoverColor,
}));
</script>

<template>
  <FullScreenLayout>
    <div class="sc-handbook" :style="containerStyle">
      <aside class="sc-handbook-toc">
        <div class="sc-handbook-toc-title">Contents</div>
        <nav class="sc-handbook-toc-nav">
          <a
            v-for="item in tocItems"
            :key="item.id"
            class="sc-handbook-toc-link"
            :class="{
              'sc-handbook-toc-link--active': activeId === item.id,
              'sc-handbook-toc-link--h2': item.depth === 2,
              'sc-handbook-toc-link--h3': item.depth === 3,
            }"
            href="javascript:void(0)"
            @click="scrollToHeading(item.id)"
          >
            {{ item.text }}
          </a>
        </nav>
      </aside>
      <main class="sc-handbook-content" v-html="htmlContent" />
    </div>
  </FullScreenLayout>
</template>

<style scoped>
.sc-handbook {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--cv-bg, #0f0f1a);
  color: var(--cv-text, #fff);
}

.sc-handbook-toc {
  flex-shrink: 0;
  width: 240px;
  overflow-y: auto;
  padding: 24px 16px;
  border-right: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  background: var(--cv-card-bg, #1a1a2e);
}

.sc-handbook-toc-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--cv-text, #fff);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
}

.sc-handbook-toc-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sc-handbook-toc-link {
  display: block;
  padding: 4px 8px;
  font-size: 13px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.6));
  text-decoration: none;
  border-radius: 4px;
  cursor: pointer;
  line-height: 1.5;
  transition: color 0.15s, background 0.15s;
}

.sc-handbook-toc-link:hover {
  color: var(--cv-text, #fff);
  background: var(--cv-hover, rgba(255, 255, 255, 0.05));
}

.sc-handbook-toc-link--active {
  color: var(--cv-primary, #4c80f0);
  background: rgba(76, 128, 240, 0.1);
}

.sc-handbook-toc-link--h2 {
  padding-left: 16px;
  font-size: 12px;
}

.sc-handbook-toc-link--h3 {
  padding-left: 28px;
  font-size: 12px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.45));
}

.sc-handbook-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 32px 48px 64px;
  line-height: 1.75;
  font-size: 14px;
}

:deep(.sc-handbook-content h1) {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px;
  color: var(--cv-text, #fff);
  letter-spacing: -0.02em;
}

:deep(.sc-handbook-content h2) {
  font-size: 20px;
  font-weight: 600;
  margin: 40px 0 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  color: var(--cv-text, #fff);
}

:deep(.sc-handbook-content h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 28px 0 8px;
  color: var(--cv-text, #fff);
}

:deep(.sc-handbook-content p) {
  margin: 8px 0;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.75));
}

:deep(.sc-handbook-content ul),
:deep(.sc-handbook-content ol) {
  margin: 8px 0;
  padding-left: 24px;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.75));
}

:deep(.sc-handbook-content li) {
  margin: 4px 0;
}

:deep(.sc-handbook-content strong) {
  color: var(--cv-text, #fff);
}

:deep(.sc-handbook-content code) {
  background: var(--cv-card-bg, #1a1a2e);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--cv-primary, #4c80f0);
}

:deep(.sc-handbook-content a) {
  color: var(--cv-primary, #4c80f0);
  text-decoration: none;
}

:deep(.sc-handbook-content a:hover) {
  text-decoration: underline;
}
</style>
