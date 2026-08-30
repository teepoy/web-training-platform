import { defineMessageCatalog } from "@/app/i18n/catalog";

export const taskTrackerMessageCatalog = defineMessageCatalog("task-tracker", {
  "en-US": {
    tasks: {
      title: "Task Explorer",
      search: "Search tasks",
      allKinds: "All task kinds",
      allStatuses: "All statuses",
      resourceLabel: "tasks",
      task: "Task",
      stage: "Stage",
      kind: "Kind",
      queue: "Queue",
      updated: "Updated",
      insight: "Insight",
      automationRun: "Automation run",
      training: "Training",
      prediction: "Prediction",
    },
  },
  "zh-CN": {
    tasks: {
      title: "任务浏览器",
      search: "搜索任务",
      allKinds: "全部任务类型",
      allStatuses: "全部状态",
      resourceLabel: "任务",
      task: "任务",
      stage: "阶段",
      kind: "类型",
      queue: "队列",
      updated: "更新时间",
      insight: "详情",
      automationRun: "自动化运行",
      training: "训练",
      prediction: "预测",
    },
  },
});
