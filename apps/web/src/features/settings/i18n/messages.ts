import { defineMessageCatalog } from "@/app/i18n/catalog";

export const settingsMessageCatalog = defineMessageCatalog("settings", {
  "en-US": {
    settings: {
      title: "Settings",
      accessKeys: "Access Keys",
      createAccessKey: "Create Access Key",
      accessKeyCreated: "Access Key Created",
      accessKey: "Access Key",
      failedToLoad: "Failed to load access keys",
      noKeys: "No access keys yet",
      createFirstKey: "Create your first key",
      prefix: "Prefix",
      created: "Created",
      createdSuccess: "Access key created",
      deletedSuccess: "Access key deleted",
      saveFailed: "Failed to save access key",
      deleteFailed: "Failed to delete access key",
      copyFailed: "Failed to copy",
      copyWarning: "Copy your access key now. You won't be able to see it again.",
      confirmDelete:
        "Are you sure you want to delete this access key? Any applications using it will lose access.",
      nameEmpty: "Name cannot be empty",
    },
  },
  "zh-CN": {
    settings: {
      title: "设置",
      accessKeys: "访问密钥",
      createAccessKey: "创建访问密钥",
      accessKeyCreated: "访问密钥已创建",
      accessKey: "访问密钥",
      failedToLoad: "无法加载访问密钥",
      noKeys: "暂无访问密钥",
      createFirstKey: "创建第一个密钥",
      prefix: "前缀",
      created: "创建时间",
      createdSuccess: "访问密钥已创建",
      deletedSuccess: "访问密钥已删除",
      saveFailed: "无法保存访问密钥",
      deleteFailed: "无法删除访问密钥",
      copyFailed: "复制失败",
      copyWarning: "请立即复制访问密钥，之后将无法再次查看。",
      confirmDelete: "确定要删除此访问密钥吗？使用它的应用将失去访问权限。",
      nameEmpty: "名称不能为空",
    },
  },
});
