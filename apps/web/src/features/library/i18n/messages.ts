import { defineMessageCatalog } from "@/app/i18n/catalog";

export const libraryMessageCatalog = defineMessageCatalog("library", {
  "en-US": {
    library: {
      eyebrow: "Data resources",
      title: "Library",
      description: "Find and manage datasets and collections in one place.",
      resourceTypes: "Library resource types",
      datasets: "Datasets",
      collections: "Collections",
      searchDatasets: "Search datasets",
      searchCollections: "Search collections",
      filters: "Library filters",
      newCollection: "New collection",
    },
  },
  "zh-CN": {
    library: {
      eyebrow: "数据资源",
      title: "资源库",
      description: "在一个位置查找和管理数据集与数据集合。",
      resourceTypes: "资源库资源类型",
      datasets: "数据集",
      collections: "数据集合",
      searchDatasets: "搜索数据集",
      searchCollections: "搜索数据集合",
      filters: "资源库筛选",
      newCollection: "新建数据集合",
    },
  },
});
