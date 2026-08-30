import { defineMessageCatalog } from "@/app/i18n/catalog";

export const adminMessageCatalog = defineMessageCatalog("admin", {
  "en-US": {
    adminInfrastructure: {
      title: "Infrastructure",
      subtitle: "Protected operator consoles for execution and storage diagnostics.",
      restrictedTitle: "Restricted operator access",
      restrictedHelp:
        "These links do not grant access. Each console must be protected by TLS and an authenticated reverse proxy or private VPN. Use the platform for normal Dataset, Model, and Automation work.",
      restrictedOperations: "Restricted operations",
      invalidTitle: "Invalid deployment configuration",
      invalidHelp: "Configure a credential-free HTTPS URL. This launch action remains disabled.",
      notConfigured: "No protected URL is configured for this deployment.",
      openConsole: "Open protected console ↗",
      deploymentTitle: "Deployment-owned configuration",
      deploymentHelp:
        "Console URLs are supplied when the web container starts. They cannot be edited here and are never synthesized from localhost or internal container addresses.",
      configured: "Configured",
      invalid: "Invalid",
      statusNotConfigured: "Not configured",
      prefectName: "Prefect UI",
      prefectDescription: "Execution infrastructure for flow runs, deployments, and worker health.",
      prefectOperation1: "Inspect flow-run state, logs, deployments, and work-pool health.",
      prefectOperation2:
        "Perform an approved retry, cancellation, or maintenance action after checking platform task state.",
      prefectOperation3:
        "Do not create, edit, or delete platform-managed deployments outside the release runbook.",
      minioName: "MinIO Console",
      minioDescription:
        "Storage infrastructure for platform artifacts, manifests, and review assets.",
      minioOperation1: "Inspect bucket, object, and version metadata during diagnostics.",
      minioOperation2: "Verify or recover artifacts only through an approved operational runbook.",
      minioOperation3:
        "Do not delete or overwrite objects, credentials, policies, or lifecycle rules from the console.",
    },
    admin: {
      title: "Admin",
      dashboard: "Dashboard",
      infrastructure: "Infrastructure",
    },
  },
  "zh-CN": {
    adminInfrastructure: {
      title: "基础设施",
      subtitle: "用于执行和存储诊断的受保护运维控制台。",
      restrictedTitle: "仅限授权运维访问",
      restrictedHelp:
        "这些链接本身不会授予访问权限。每个控制台都必须由 TLS 和经过身份验证的反向代理或专用 VPN 保护。日常的数据集、模型和自动化工作请使用平台功能。",
      restrictedOperations: "受限操作",
      invalidTitle: "部署配置无效",
      invalidHelp: "请配置不含凭据的 HTTPS URL。在此之前，启动操作保持禁用。",
      notConfigured: "此部署尚未配置受保护的 URL。",
      openConsole: "打开受保护的控制台 ↗",
      deploymentTitle: "由部署管理的配置",
      deploymentHelp:
        "控制台 URL 在 Web 容器启动时提供，不能在此编辑，也不会根据 localhost 或内部容器地址自动生成。",
      configured: "已配置",
      invalid: "无效",
      statusNotConfigured: "未配置",
      prefectName: "Prefect 界面",
      prefectDescription: "用于流程运行、部署和工作进程健康状态的执行基础设施。",
      prefectOperation1: "检查流程运行状态、日志、部署和工作池健康状态。",
      prefectOperation2: "检查平台任务状态后，执行已批准的重试、取消或维护操作。",
      prefectOperation3: "不得在发布运行手册之外创建、编辑或删除平台管理的部署。",
      minioName: "MinIO 控制台",
      minioDescription: "用于平台产物、清单和审核资源的存储基础设施。",
      minioOperation1: "在诊断期间检查存储桶、对象和版本元数据。",
      minioOperation2: "只能通过已批准的运维运行手册验证或恢复产物。",
      minioOperation3: "不得从控制台删除或覆盖对象、凭据、策略或生命周期规则。",
    },
    admin: {
      title: "管理",
      dashboard: "仪表盘",
      infrastructure: "基础设施",
    },
  },
});
