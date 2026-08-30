# Domain Context

## Glossary

### Library

普通用户查找、筛选和创建 Dataset 与 Collection 的统一数据资源工作区。Library 统一入口和基础查询语境，但不合并两种资源的身份、列表或生命周期。

Avoid: 将该入口称为 Data，或把 Library 理解为新的持久化资源类型。

### Resource automation

具有独立 ID、状态和运行历史，并绑定一个必需目标资源的自动执行规则。用户从目标资源页面创建目标导向的操作；规则继承目标资源权限，目标归档或删除后停止产生新运行，但自动化记录与既有运行历史保留用于审计。

Avoid: 用它指代组织级的任意工作流编排。

### Automation recipe

产品为某一类目标资源提供的受限自动操作，例如更新 Collection、训练 Dataset 或使用 Model 预测。Recipe 是完整且经过验证的能力单元；它声明适用资源和允许的 run mode，用户不能任意拼接底层 trigger 与 action。

Avoid: 把通用工作流中的任意步骤或 Prefect flow 直接称为 automation recipe。

### Run mode

用户选择资源操作何时运行的界面概念，例如按时间运行或在资源相关事件发生时运行。不同 run mode 可以由不同的内部 trigger adapter 实现，不要求合并为一个通用后端触发器。

Avoid: 在一般用户界面中使用 Schedule、Sensor 或 Subscription 表达 run mode。

### Trigger adapter

把时间或外部事件转换为 resource automation 运行请求的内部技术组件。它属于执行机制，不是一般用户需要单独创建或管理的产品对象。

### Event source

由系统注册或管理员配置、向 trigger adapter 提供资源相关事件的数据连接。一般用户只选择当前资源与 recipe 支持的事件运行方式，不创建 Sensor 或管理底层 polling/checkpoint。

### Source connector

由 Org admin 在 `Admin > Connections` 配置的外部数据连接。Connector 声明 Source record schema、filter capability、Backfill 时间字段、health、live-discovery watermark 和 operator-controlled polling/reconciliation frequency；普通用户只能在 Membership rule 中选择可用 connector。

### Source record

任意只读 upstream 或 event source 中被发现、可导入为 Dataset 的 provider-owned 记录。SC provider 中它对应 `/sc/preview` 的 inspection/wafer/layer summary，并可包含多个 defect patch 样本；通用 Collection 与 Automation contract 不使用 SC-specific 名称。

Avoid: 在通用领域模型中使用 Patch record，或把 Source record 等同于单个 defect/patch 样本。

### Source record identity

Source connector 为一条 provider-owned 记录提供的稳定 opaque key，与 connector ID 一起构成平台中的来源身份。显示名称、查询字段和内容 hash 都不能替代该身份。

### Dataset import identity

在一条 Resource automation/Collection 导入链路内，由 Source record identity、Source version 和 Import profile version 共同确定的幂等身份。它只防止同一链路重放或并发时重复创建 Dataset，不使不同 Automation 或 Collection 共享 Dataset。

### Membership rule

从一个注册的 event source 中匹配 Source record，并把导入结果 Link 到 Collection 的版本化规则。每条 rule 绑定一个 Source connector 与一个 Import profile，并使用 provider 声明的字段、类型和操作符构造通用 `All/Any` 条件树。一个 Collection 可以同时拥有手动成员和多个 membership rule；它们最终产生同一种 Collection member，但保留不同的来源 provenance。

### Backfill

使用一个明确的 membership rule version 和用户指定的历史时间范围，发现并处理既有 Source records 的独立操作。启用 membership rule 本身只处理启用后出现的新记录；历史处理不会作为隐藏的启用副作用发生。Provider 声明业务时间字段；用户选择 IANA timezone，API 将范围规范化为 UTC 半开区间 `[start, end)`。

Backfill 固定使用启动时的 rule version，使用独立 cursor，且不推进或回退实时发现 watermark。它可以和实时发现并行，并在全部内部 execution windows 结束后最多发布一个合并后的 Collection Revision。

### Execution window

Backfill 内部用于限制单次查询批次和并发的运行时切片。Execution window 不是长期业务身份，不向一般用户暴露为 Partition，也不单独发布 Collection Revision。

### Discovery receipt

证明某个 membership rule 已处理特定 Source record 与 import profile 的幂等记录。相同 rule 下的重放返回第一次处理结果；同一 Collection 的另一个 rule 保留独立 receipt 但通过 Collection-level source identity 复用现有 member，不重复 Link。

### Import receipt

对一个 Dataset import identity 的链路级幂等记录，包含 staging、attempt 与最终 Dataset 结果。同一 Automation 链路的重复请求加入正在执行的 Import、复用 Ready 结果，或 Retry 已失败的同一 Import；其他 Automation 各自创建 Dataset。

### Discovery run

一次检查和处理一批 Source records 的可追踪运行。一个 run 最多发布一个 Collection Revision；成功导入的成员可以发布，失败记录单独保留错误并等待重试。

### Membership suppression

用户显式移除规则发现成员后留下的阻止重新加入记录。只要 suppression 未被用户清除，后续匹配同一 Collection 与 Source record 的 Discovery 就记录跳过，而不是再次导入或 Link。

### Re-import

Source record 在首次导入后发生变化时，由用户显式创建新 Dataset Revision 的操作。输出契约不兼容时 Re-import 才创建新的 Dataset；任何情况都不原地改写旧 Dataset Revision。

### Automation run history

Resource automation 已产生运行的不可变审计记录。目标资源归档、删除或规则暂停后，历史仍应保留并可从全局运行视图查询。

### Automation overview

跨资源查询、暂停、Retry 和检查 Resource automation 历史的全局管理表面。它不是脱离目标资源创建通用 Automation 的入口。

### Collection head

Dataset Collection 当前可编辑的成员与规则定义。修改 head 不会改写已经发布的历史定义记录；训练和预测记录启动时选择的发布记录，但第一阶段仍解析成员当前数据。

### Dataset revision

Dataset 在一次成功导入、Re-import、标注同步或批量编辑操作结束时自动发布的轻量变更记录。记录本身不可修改，包含操作审计、provenance 与当前数据逻辑引用，但第一阶段不复制样本/标注数据，也不承诺完全可复现。训练和预测可以记录启动时观察到的 Dataset Revision 作为 provenance；Collection Revision 不固定成员 Dataset 数据版本。

### SC class mapping

平台统一定义的 SC 原始整数 `class_number` 到用户可读类别名称的展示映射。原始整数仍是查询、过滤、传输和导出的稳定标识；该映射不属于 Dataset metadata、annotation taxonomy 或 model label space。

Avoid: 为不同 Dataset、Collection、组织或 connector 创建各自的 SC class mapping。

### Collection data contract

Collection 成员共同满足的目标 view、任务 schema 与 canonical label space 契约。兼容性由 Dataset adapter 提供的能力判断，而不是要求成员拥有相同的 `dataset_type` 名称。

### Collection purpose

用户创建 Collection 时选择的业务用途模板，例如 Image Classification。Purpose 由产品 descriptor 提供，并解析为精确的 Collection data contract，普通用户不直接填写底层 view ID 或 schema。

### Draft collection

已经创建但尚未成功发布第一个 Revision 的 Collection。Draft collection 可以继续配置成员和规则，但不能作为训练或预测输入。

### Collection revision

Collection head 在一次成功发布时产生的不可修改记录，固定成员 identity、顺序、规则与映射。它不固定成员 Dataset 行、annotation 或 upstream 字段；Classify、training 与 prediction 始终读取这些成员的当前数据，因此 Revision 不是数据 time-travel 机制。

Avoid: 把 revision 理解为用户需要手工维护的 Collection 副本，或允许原地编辑 revision。

### Collection default model

Collection 为自动预测选择的、固定到具体 Model identity/version 的默认模型。修改默认模型只影响后续预测；自动训练得到的新模型先作为 candidate，不会自动替换默认模型。

### Prediction coverage status

Collection 中每个成员 Dataset 相对于 default model 和当前 Dataset Revision 的预测覆盖状态：`Current` 表示成功预测同时使用当前默认 Model 与当前 Revision；`Model mismatch` 表示使用了其他 Model；`Data outdated` 表示预测属于旧 Dataset Revision；`Not predicted` 表示没有成功预测。后三种状态必须醒目标记，并允许多选后用当前默认 Model 和 Revision 重跑。

### Candidate model

自动训练成功产生、但尚未替换 Collection default model 的模型。Candidate 保留训练所用 Collection Revision 和训练运行 provenance；在评估与 Promote 方案明确前，自动训练不得自动切换默认模型。

所有 Candidate Models 均保留用于后续比较与回退分析；界面可以突出最新 Candidate，但不能用新 Candidate 覆盖或删除旧记录。

### Product work surface

普通用户完成平台业务工作的界面。Label Studio 在支持其标注能力的 Dataset 上作为上下文 work surface 出现，不作为独立的全局管理入口。

### Classify workspace

SC Dataset 或 SC Collection 中浏览、筛选、抽样和标注缺陷样本的全屏 Product work surface。资源详情中的 `Classify ↗` 是该 workspace 的直接导航入口，不渲染中间预览页；Dataset 直接打开自身样本，Collection 使用所选 Revision 的成员并始终读取这些成员的当前数据。

Avoid: 将 SC Samples 呈现为通用原始行表格，或把 Classify workspace 当作独立资源。

### Annotation sampling pipeline

Classify workspace 中按用户声明顺序执行的 17 类抽样规则。每一步只接收上一步留下的行，因此移动规则会改变结果。默认先执行 `Maximum per Die = 10`，再执行 `Maximum per Wafer = 200`；浏览器为当前用户单独保存该 pipeline，不与导出偏好共用。

### Review sampling

SC 结果导出前可选执行的有序抽样 pipeline。默认 `Maximum per Wafer = 100`，并使用独立于 Annotation sampling pipeline 的浏览器偏好。Extra Filter 在规则 pipeline 前执行；Annotation、Prediction 或 Final Class 结果来源决定空结果排除、分布展示、分布抽样和最终导出类别。

Avoid: 将 Review Sampling 称为 Annotation Sampling，或让它与 Classify workspace 共用同一个 localStorage 配置。

### Image resolution service

把一组顺序的领域图片引用解析为原始图片 bytes、content type 与稳定错误的共享 data-plane 服务。Display、Prediction 与 Training 使用语义分离的入口、资源预算和缓存 namespace，但共用同一套设备入口、下载与解析契约。

Avoid: 把图片 decode、resize、channel stack、tensor 转换或模型推理称为 image resolution。

### Prediction image stream

一次 Prediction run 与 Image resolution service 之间的有界双向 gRPC 流。客户端持续提交顺序 request batches，服务端在有界并发解析后按 sequence 返回 result batches，并通过 stream flow control 向上游施加 backpressure。

### Training image stream

与 Prediction image stream 共享图片解析 primitive，但以独立 gRPC 入口表达 Training 语义、指标、并发预算和缓存生命周期。第一阶段只要求职责分离，不要求复制 Prediction 专用优化。

### Export image stream

含图片的 Prediction Export 与 Image resolution service 之间的独立有界 gRPC 流。它可以只请求导出格式需要的 role，共享 streaming engine 但不伪装成 Prediction，也不占用 Display 预算。

### Image stream context

一条 Prediction 或 Training image stream 内显式打开的 Inspection 解析上下文。客户端使用 stream-local context ID 引用 `(inspection_time, wafer_key)`；服务端在打开时解析一次 `eqp_id`，关闭或断流时释放该上下文持有的资源。

### Equipment image entry

一个精确 `eqp_id` 在代码注册表中对应的图片来源入口。多个明确列出的 `eqp_id` 可指向同一 EntryFactory；未知设备、重复注册或空 ID 直接失败。Entry 提供 Image artifact downloader 与 Image artifact parser，不根据运行时配置、扩展名或 sniffing 改变解析逻辑。

### Image artifact downloader

设备入口中把 upstream source 解析为带稳定 identity 与 version/etag 的 ArtifactRef，并能将对应文件或目录流式写入指定的本地 staging 位置。Downloader 不决定 TTL、LRU、Janitor 或共享缓存生命周期。

### Image artifact parser

设备入口中从已在本地可见的 artifact 按设备规则解析所需图片，返回原始 bytes、content type 和 item error 的组件。Parser 不下载 source、不管理缓存，也不执行模型预处理。

### Image artifact cache

Image resolution service 中在下载前使用 ArtifactRef 查找或发布本地文件/目录的统一机制。Display、Prediction 与 Training 共享 Cache Manager 契约，但使用独立目录、容量、TTL、并发预算与指标。同一 cache key 只允许一个 downloader 在锁内流式写入临时位置并原子发布；其他请求等待后复用结果。

ArtifactRef 的 revision 必须来自 source：对象存储优先使用 VersionId 或 ETag，可证明可靠时可使用 source `mtime + size`；目录需要 provider 给出 generation、manifest revision 或可靠的整体更新时间。下载后本地文件的 mtime 只用于 TTL/LRU，不能证明 source freshness。

### Operator console

用于检查执行基础设施或存储基础设施的管理界面。Prefect UI 和 MinIO Console 是 operator console，不进入一般用户导航。
