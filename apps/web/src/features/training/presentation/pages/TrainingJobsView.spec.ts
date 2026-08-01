import { flushPromises } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { NMessageProvider } from "naive-ui";
import { http, HttpResponse } from "msw";

import { useOrgStore } from "@/features/auth/application/org";
import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";

import TrainingJobsView from "./TrainingJobsView.vue";

const GlobalJobsView = defineComponent({
  render: () =>
    h(NMessageProvider, null, {
      default: () => h(TrainingJobsView),
    }),
});

const GatedJobsView = defineComponent({
  render: () =>
    h(NMessageProvider, null, {
      default: () => h(TrainingJobsView, { allowTrain: false }),
    }),
});

async function mountJobsView(component: typeof GlobalJobsView) {
  server.use(
    http.get("/api/v1/training-jobs", () => HttpResponse.json({ items: [], total: 0 })),
    http.get("/api/v1/trainers", () => HttpResponse.json([])),
  );
  const mounted = await mountWithProviders(component);
  useOrgStore(mounted.pinia).setCurrentOrg("org-1");
  await flushPromises();
  return mounted.wrapper;
}

describe("TrainingJobsView", () => {
  it("enables global job creation when allowTrain is omitted", async () => {
    const wrapper = await mountJobsView(GlobalJobsView);
    const startButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Start New Job"));

    expect(startButton).toBeDefined();
    expect(startButton!.attributes("disabled")).toBeUndefined();
  });

  it("keeps the dataset readiness gate when allowTrain is false", async () => {
    const wrapper = await mountJobsView(GatedJobsView);
    const startButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Start New Job"));

    expect(startButton).toBeDefined();
    expect(startButton!.attributes("disabled")).toBeDefined();
  });
});
