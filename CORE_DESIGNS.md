# 核心设计

本文是项目的核心设计决议记录。其他文档、`AGENTS.md`、README、代码注释或既有实现与本文冲突时，必须先暴露冲突，并修正文档或取得新的设计决议。

本文可以在同一未提交变更中被修订；这不算偷偷修改。提交前必须让用户看到 `CORE_DESIGNS.md` 的完整 diff，并说明哪些旧决议被覆盖、收窄或废弃。未经用户明确要求，不允许提交本文修改。

## 0. 失败语义与隐式行为

除非用户明确要求，或本文已有设计决议明确要求，否则不允许新增 fallback、隐式 limit、assumption 或 default。缺少配置、能力、参数、数据或设计决议时，应显式报错、暴露冲突或要求新的设计决议，而不是用兜底行为掩盖问题。

确实需要限流、超时、批量大小、并发上限或兼容 fallback 时，必须把它作为显式产品/运行时设计写清楚，并说明触发条件、可观测信号和不满足条件时的失败方式。

## 1. 系统边界

平台分为五个主要运行层：

| 层                   | 包                                                   | 职责                                                                                            | 禁止事项                                                        |
| -------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Control plane        | `apps/api`                                           | HTTP API、权限、业务参数校验、runtime capability 查询、任务创建、状态与结果持久化、runtime 调度 | API route 不执行训练/预测 callable                              |
| Runtime services     | `services/*`                                         | out-of-process trainer、predictor、image/parser/upstream adapter 等重依赖运行时                 | 不 import `apps/api` 内部 service/repository/ORM/FastAPI router |
| Data plane interface | API 暴露的窄接口 / manifest / object storage handoff | 向 runtime services 提供 dataset view、artifact、prediction commit、progress report 等稳定边界  | 不暴露 API module 内部对象或把内部 Python service 当 SDK 使用   |

### Runtime Service 边界

训练、预测、嵌入等带 Torch/CUDA/大型图像依赖的执行逻辑属于 runtime worker/service，不在 HTTP route 请求路径执行。API control plane 负责创建任务、校验权限和参数、按 operation 对应的直接 deployment 提交执行、持久化业务状态和提供前端查询表面。当前 SC compatibility worker 的轻量注册函数可以位于 `apps/api/app/modules/sc`；重 ML 依赖仍只在被选中的注册函数内延迟 import，不得进入 HTTP server image 的必需依赖。

- `libs/ml` 是可选的同进程 ML implementation/data-loading library，不是 transport
  contract。API-local compatibility runtime 只能在选中的 executable callable 内
  延迟导入它；跨进程边界仍使用 manifest、OpenAPI、protobuf 或 Arrow contract。
- 未来 SDK/runtime service 边界优先使用 OpenAPI、protobuf/gRPC、Arrow schema/manifest 等生成或传输 contract，而不是手写共享 Python DTO 包。
- Runtime service 不 import `apps/api/app/modules/*` 内部 service、repository、ORM model 或 FastAPI dependency。
- API 可以提供 gRPC/HTTP 等窄 data-plane 接口，也可以返回 manifest 与 signed object-store refs 让 runtime 批量读取；大批量图片/Parquet 不应强制走逐行 RPC。
- Job progress、artifact metadata、prediction commit 等通过稳定 transport contract 回写 API，不通过共享内存对象或 API 内部 Python 类。
- SC 的算法注册、Prefect flow/task 和 executable adapter 可以由
  `apps/api/app/modules/sc` 持有；Torch/torchvision/Ultralytics 内核位于可选
  workspace library `libs/ml`。

目标执行拓扑：

```text
apps/api -> data plane interface / object storage manifest
runtime service -> data plane interface / object storage manifest

HTTP API 请求路径不直接执行 trainer/predictor callable
runtime service 不直接 import apps/api internals
```

### SC SQL Data Provider 隔离

SC 大表查询与普通 HTTP API 必须运行在不同进程和不同容器中：

- `app.main:app` 只提供 control-plane HTTP API；`app.sc_data_provider_main:app` 只提供 `/api/v1/sc/data/**`、健康检查与就绪检查。
- Data provider 使用独立最小 composition root，只装配数据库 session、Redis、SC upstream 与 dataset storage；禁止复用普通 API 的完整 `build_app_context()`。
- 查询协议固定为 HTTP `POST` + 参数化只读 DuckDB SQL + Arrow IPC Stream；变更通知使用 SSE。浏览器不得依赖 Perspective 或其他 WebAssembly SIMD runtime。
- SQL 只能访问当前授权 scope 内的只读 `samples` 与 `review_images` view；AST policy 和 DuckDB connection 必须同时禁止 DDL、DML、外部文件/网络扫描、extension 安装与加载。
- Selection 是前端 workbench 状态和参数化查询约束，不是服务端数据列；禁止重新引入 `map_in_selection`、`table_in_selection` 或通过表更新保存 UI selection。
- Annotation/prediction 先持久化，再通过 Redis 原子递增全局 scope revision 并发布 invalidation。查询返回自身 revision；浏览器丢弃低于已知 revision 的响应。
- 不缓存最终 SQL result。共享 object cache 只保存不可变 base、review-image 与 overlay Parquet/Arrow object，并用 Redis build lock、metadata、lease 与 cleanup leader 协调。临时文件必须原子 rename 后才可见；有 lease 的 object 禁止清理。
- Compose 使用独立 `sc-data-provider` 服务，由 Uvicorn `--workers 4` 在单个 `8001` socket 上管理四个 worker；Nginx 只代理 `sc-data-provider:8001`，不做容器内多端口负载均衡。
- Kubernetes 每 Pod 只运行一个 Uvicorn worker，由 Deployment replicas 和 Service 分流。`emptyDir` cache 与 Redis cache metadata 按 Pod namespace 隔离，scope revision 在所有 Pod 间共享。
- 每个 worker 只拥有一个 DuckDB connection、一条单线程执行队列和独立 spill 目录。内存、spill、响应大小、SQL timeout、cache 水位与 TTL 必须在配置和部署清单中显式声明。
- `/health` 与 `/ready` 每次调用都以 info 级别记录当前 worker RSS；`/ready` 在超过 `SC_DATA_PROVIDER_MAX_RSS_MB` 时返回 503，容器/Pod 的硬内存 limit 作为最终保护。
- Perspective WebSocket、Supervisor、watchdog、多端口 healthcheck 与相关包不属于目标架构，不得作为失败 fallback 恢复。

> **迁移说明：** 旧版独立的 `gpu-worker` / `inference` / `embedding` 服务已并入 `apps/api` Prefect flow。原 `apps/worker`、`apps/inference`、`apps/embedding` 目录已移除。

SC 本地执行能力采用 module-owned algorithm + optional library：

- `apps/api/app/modules/sc` 可以在算法局部模块中共同维护 capability metadata、
  executable binding、Prefect flow/task 和 runtime adapter。
- `libs/ml` 只拥有 Torch、TorchVision、Ultralytics 模型、训练与推理
  内核；禁止反向 import `app.*`、Prefect、repository、ORM 或 FastAPI dependency。
- `ml_library.models` 仅为同进程内核 value model，不是 transport contract。SC 新增
  跨进程/跨语言接口时必须并入现有 `libs/protos`，优先使用 protobuf、Arrow
  schema/manifest 等 language-agnostic 定义，禁止新建 Python-only contract lib。
- 这一 SC 例外不把 optional library 变成通用 shared runtime contract；未来
  production runtime 仍可迁移为 `services/*` out-of-process runtime，通过
  manifest、OpenAPI/protobuf 和 Prefect deployment 接入。

## 2. 后端组织

后端按 DDD / 模块边界组织。

- Route handler 保持薄层，只做协议解析、依赖注入和错误映射。
- 业务逻辑进入 module service；持久化进入 repository。
- 共享基础设施只包含 DB engine/session、对象存储、外部 client 等 infra，不承载模块私有 service/repository。
- `apps/api` 使用 `injector` library 做 composition。模块间依赖通过显式 Protocol/port 注入，不直接读取 sibling module 内部对象，也不跨模块注入具体 service class。
- Registration 是模块边界的例外，只允许触发注册副作用或导出 descriptor，不允许借 registration 调用 sibling module 业务逻辑。
- Module domain model 归属所在 module，例如 `apps/api/app/modules/sc`。不要为了“未来可能复用”提前创建 shared Python contracts / ML packages；有真实外部 consumer 时优先以生成 contract 接入。

API 可以通过调度器或 runtime service client 创建后台任务、查询状态、读取日志摘要。具体编排机制可以是 Prefect、service queue、gRPC job API 或其他运行时协议；无论采用哪种机制，API route 都不直接执行可训练/可预测 callable。

## 3. Runtime 与任务状态

后台执行系统是运行时执行状态来源。API 是产品业务状态事实来源。前端只通过平台 API 查询任务，不直接消费 Prefect、service queue、runtime service 的内部 payload。Prefect 是当前 deployment transport 和 execution-state backend，不是 trainer/predictor 注册模型的必需抽象。

通用层不定义训练/预测步骤图、数据集构建流程、materialization 流程或 prediction chunk 策略。它只提供 submission/dispatch、runtime context 构建、执行入口和平台任务状态接线。业务操作如需组合 train + predict，由拥有该算法的 module 注册一个组合 callable，不由中心 orchestration service 推断步骤。

长任务状态边界：

- API 创建平台任务，校验权限和参数，持久化业务状态，并将任务交给后台编排或 runtime service。
- CPU runtime service / worker 执行后台/大批量导入、传感器、数据导出等 CPU 负载。
- 低延迟、小批量导入可以由 API service 受限执行，但必须显式设置样本数、超时、并发和资源保护边界；route handler 仍保持薄层，不直接承载导入实现。
- GPU runtime service 执行训练、预测、嵌入等 GPU 计算，并通过 data-plane contract 读取 dataset view、提交 prediction/artifact/progress。
- Task Tracker 表达产品视角的任务阶段、完成状态和产物位置。
- Prometheus/Grafana/Loki 是运维观测系统，不是产品任务状态系统。
- Training 的数据相关 readiness preflight 在已提交的 durable workflow 内执行，HTTP
  提交路径只做权限、source metadata、capability 与参数校验，不扫描 sample 表、manifest
  或 raw Parquet。Preflight 必须保持 `assess_classes` 的类别检查语义；图片可读性仍由具体
  trainer runtime 负责。Preflight 失败写入平台 job 的 failed 状态与事件，不恢复同步
  HTTP 422 扫描。
- API lifespan 运行 training status reconciler，从数据库恢复所有具有 external execution
  ID 的 queued/running job，并以显式配置的间隔对照 execution backend 修正平台业务状态。
  单个日志监听协程不是状态事实来源；API 重启或日志读取异常不得让任务永久停留在
  queued/running。

实时进度面向前端首选 SSE。WebSocket 不是默认方案。

Prometheus label 不允许包含 `job_id`、`dataset_id`、`model_id`、`user_id`、`org_id` 等高基数字段。单任务细节进入 Prefect、Task Tracker 或结构化日志。

### Resource Automation

用户自动化采用 target-bound、context-first 模型。每条 Resource automation 必须绑定
一个 Dataset、Collection、Model 或其他目标资源，并从该资源页面选择产品注册的受限
recipe。普通用户配置按时间或资源事件运行等业务化 run mode，不创建 Schedule、Sensor
或 Subscription，也不能任意拼接 trigger/action。底层机制可以继续使用独立 trigger
adapter；Schedule/Sensor 是内部实现术语。

- 全局 `Automations` 页面只做跨资源查询、状态、暂停/恢复、Retry 和历史检查，不提供
  无目标通用工作流 builder。旧 `/schedules` 和 `/sensors` 页面不保留兼容跳转。
- Event source 和 Source connector 由系统注册或 Org admin 在 Admin 配置。普通用户只选择
  当前资源/recipe 支持的连接与运行方式。
- 同一 automation 的 cron occurrence 与活跃 run 重叠时记录 skipped；事件重叠时合并为
  一个 pending rerun。取消只停止新 child work 并 best-effort 取消已派发 work，不回滚已
  完成结果；Retry 只处理失败/未完成项并固定原始输入，使用最新配置必须创建新 run。
- 用户手动触发的 prediction child work 使用高优先级 work queue；自动新增成员 prediction
  使用低优先级 work queue。优先级只影响尚未开始的任务，不抢占运行中任务；用户手动
  Retry 仍使用高优先级队列。
- Automation 继承目标资源权限和归档状态。组织成员可以编辑和触发 Collection 规则、
  Backfill、预测与 candidate training；Source connector 和基础设施配置只允许 Org admin。
  高成本操作必须展示目标、固定 Model/Snapshot/Rule 和预计 child work 后显式确认。
- 目标归档后停止新运行但保留历史；恢复目标不自动恢复 automation。所有 mutation/run
  记录 actor 与 org。失败、Partial 和 Needs attention 先通过站内通知、资源 Activity 与
  全局 Automations 暴露，不在第一阶段加入邮件/Webhook。

## 4. Dataset / View / Storage

Dataset 相关概念分四层，不能混用：

1. `storage_mode`：物理存储方式，例如 `db_full`、`file_shard_sparse`。
2. `dataset_type`：语义类型，例如 classification、detection、vqa。
3. `view contract`：trainer/predictor 实际消费的数据视图。
4. trainer/predictor/model：运行时能力与模型产物。

`storage_mode` 与 `dataset_type` 正交。任何涉及样本枚举、训练、预测、导出、Label Studio 同步的逻辑都必须显式检查 `storage_mode`，不能从 `dataset_type` 推断。

`view contract` 是 dataset 与 runtime 的兼容边界。Trainer/predictor 只声明自己消费的 view，不直接依赖某个 dataset type 的内部存储结构。

Dataset 是稳定逻辑资源；首次成功导入、兼容 Re-import、标注同步和批量编辑在操作边界
发布轻量 Dataset Revision 变更记录。Revision 记录本身不可修改，但第一阶段只保存操作
审计、provenance 和指向当前数据的逻辑引用，不复制每次变化后的样本、标注或图片，也不
承诺完整可复现。训练和预测记录提交时观察到的 Dataset Revision ID 作为 provenance，
runtime 仍解析 Dataset 当前数据；需要完全冻结输入时应另行设计低频、显式的 frozen
release，而不是让每个高频 Revision 自动物化。输出 contract 不兼容的 Re-import 创建新
Dataset。历史 Dataset 不批量回填 Revision、import identity 或内容指纹；首次进入
revision-aware 写入/任务流程时才按需建立 Revision #1，不伪造更早历史。

平台不通过逐图片 hash 或 Dataset 内容 fingerprint 判重。自动导入只在一条
Resource automation/Collection 链路内使用 Source connector、provider record key、
Source version 与 Import profile version 建立 Import receipt 和数据库唯一约束，防止
重放/并发创建重复 Dataset；不同 Automation/Collection 不共享自动导入的 Dataset。
Dataset name 不是 identity。

### Dataset Collection 与 Snapshot

Collection 是 Dataset membership 的组合资源；Dataset 与 Collection 在 `Library` 中
统一入口但保持独立身份、列表、分页和生命周期。Collection 声明 target view、task
schema 和 canonical label space 组成的数据 contract；成员兼容性由 Dataset adapter
能力判断，不要求 `dataset_type` 名称相同。显式 label mapping 必须覆盖每个 source label
或标记 Ignore，并在发布前展示排除计数；不得模糊自动映射。

- Collection head 是可编辑定义，Collection Snapshot/Revision 是不可修改的发布记录。
  Snapshot 记录发布时观察到的 Dataset Revision ID、规则/映射版本、组合 manifest、
  汇总与审计，但第一阶段的 `source_resolution` 为 `observed`，不宣称成员数据已冻结或
  可复现。Snapshot 不复制全部成员行或图片；runtime 在启动时解析当前成员数据，完整
  merge 只能作为可清理重建的 cache，不是归档事实来源。
- 空 Collection 可以作为 Draft，但不发布空 Snapshot。成功的 manual batch、Discovery
  或 Backfill 每次至多自动发布一个 Snapshot；用户不手工创建 Revision。失败 publication
  保留 pending head changes 和最后成功 current Snapshot。定义和观察到的 Dataset
  Revision 集合不变时结果为 unchanged。
- 共享 Dataset 发布新 Revision 时，引用它的 Collection 只显示 Update available，不自动
  发布 Snapshot。用户显式 refresh 后记录所有成员最新兼容 Revision，并发布一个
  Snapshot；中间 Dataset Revisions 仍保留审计历史。该 refresh 第一阶段不自动触发预测、
  reconciliation 或 candidate training。
- Membership 可以手动 Link，也可由版本化 typed rule 从一个 Source connector + Import
  profile 发现 Source record。Rule 只使用 provider descriptor 声明的字段/类型/operator
  和通用 All/Any 条件树，不接受 SQL、JSONPath 或 Python。自动发现第一阶段只增加成员，
  不自动 unlink；手工移除规则成员会建立 Collection-scoped suppression。
- 同一 Collection 中相同 Source identity 只保留一个活跃规则成员；不同 Collection 各自
  导入 Dataset。Rule activation 只处理未来数据，历史范围通过独立 Backfill 处理。
  Backfill 固定 rule version、connector、Import profile、IANA timezone 与 UTC `[start,end)`
  范围，使用独立 cursor，不推进 live watermark；内部 execution window 不暴露为产品
  Partition。Partial success 可发布成功成员，失败 Source record 单独 Retry。
- Collection 可固定 exact default Model version。新 admission 发布 Snapshot 后只预测新
  Dataset，不全量重跑；Model 变更不自动重跑既有成员。Coverage 必须区分 Current、Model
  mismatch、Data outdated 与 Not predicted，并支持选择性 reconciliation。自动训练只在
  membership/definition/mapping Snapshot 变化后按用户选择的每日/每周本地时间 gated
  运行，产出 Candidate Model，不自动替换 default Model。仅 Dataset Revision refresh 不
  标记 candidate training dirty。

Dataset view samples 必须通过 dataset registry / dataset class / adapter 动态投影。不能为每个 view 新增 hardcoded route 作为主要集成方式。

Dataset operator/storage 层拥有 `db_full`、`file_shard_sparse`、Parquet shard、manifest、locator 等持久化细节。SC import 这类 domain ingest 只负责 upstream/domain model 到通用 dataset sample/import stream 的转换，不直接拥有 sparse shard 或 Parquet 写入逻辑。

`DatasetStorageAgg` 是 dataset storage 的唯一聚合入口。调用方通过 `DatasetStorageFactory.open(dataset_id, org_id)` 按 `storage_mode` 打开具体实现，然后使用统一 Protocol 完成样本枚举、批量写入、标注、预测结果、特征、删除和必要的存储级 materialize 操作。Storage materialize 只返回 data-plane manifest、materialized file 或 object reference，不返回 Torch/Hugging Face Dataset。训练、预测、导出、agent/classify 等批量读路径不得绕过它去直接使用 `SqlRepository`、`SampleAccessFactory`、`DatasetSampleService`、`RuntimeMaterializer` 或 ad-hoc shard reader。

`DatasetStorageAgg.list_samples(return_lazyframe=True, ...)` 是 API 内部 storage 聚合层的批量读标准表面。面向 out-of-process trainer/predictor 时，API/data-plane 应把对应 view 暴露为稳定 transport contract、Parquet/Arrow manifest 或 signed object-store refs；runtime service 不直接 import `DatasetStorageAgg`、`DatasetStorageFactory`、`SampleORM` 或 API repository。`with_labels=True` 由 storage/data-plane 把最新标注并入 view。View/domain projection 属于 trainer/predictor、domain aggregate 或 data-plane adapter，不属于物理 storage 层。

Storage、data-plane、materializer 的主数据路径必须是 bulk/table-first：优先使用 Polars `LazyFrame`，靠近消费端可按需要 materialize 为 `DataFrame` 或 Arrow `Table`。如需额外 schema、capability、manifest metadata，应包装 lazyframe/dataframe/arrow table 或引用其 schema，不得把大数据路径转换成 dataclass/Pydantic row DTO 列表。除非明确证明数据量小且有边界，禁止对样本行做 Python `for` 循环逐行处理；应使用 LazyFrame/DataFrame/Arrow scan、projection、join、batch、streaming writer 等批量操作。Data-plane manifest 的第一版 contract 见 `docs/architecture/data-plane-manifest-contract.md`。

Runtime consumer 必须显式选择数据加载函数，不提供按规模猜测的统一 factory：
小且有明确上限的 Parquet 输入使用 `collect_parquet_dataset`；需要 map-style
indexed shuffle 的中等数据先 materialize 为带整数 `__row_index` 的 Arrow IPC
stream，再使用 `open_hf_arrow_dataset` mmap；大数据/预训练使用
`stream_parquet_dataset`。文件与 manifest 的生命周期由调用链外层显式管理。

`DatasetAgg` 是 domain-specific 聚合层：它包装一个 `DatasetStorageAgg`，承载 SC 等业务语义（如 wafer point 计算、`defect_id` 批量标注、domain 预测编排），但不拥有物理存储、manifest、Parquet shard 或通用 annotation/prediction persistence 细节。新的 domain 能力应优先放在对应 `DatasetAgg`，不是塞进通用 storage Protocol，也不是在 route/service 中新增 hardcoded switch。

SC Import as Dataset 当前使用 API service 内的 direct sparse import 路径：`upstream.list_samples(...)` → domain row normalization → sparse shard writer / manifest update。SC import 不再注册或依赖 Prefect flow；Prefect CPU worker 仍保留给 sensors、dataset drain 等后台任务。该 direct import 路径不能成为训练/预测/导出读取 fallback，也不能重新引入旧 SampleAccess/RuntimeMaterializer 层。

平台 sample storage identity 与 module domain identity 必须解耦。`Sample.id` 是平台存储身份；SC `defect_id`、`sample_id`、`inspection_time`、`wafer_key` 等是 domain/upstream identity，不应默认写入全局主键。

通用 Dataset-owned 嵌入图片仍通过平台后端的认证 route 表达；SC 图片是独立的
display/runtime data-plane。Web gateway 将 `/api/v1/sc/images/...` 与
`/api/v1/sc/sprites/...` 直接转发到 image-parser，FastAPI 不注册 SC bytes proxy，也不提供
Python fallback。image-parser HTTP route 必须验证与 API 相同密钥签发的 HS256 token；前端
`<img>` / blink table / preview grid 不能携带自定义 header，因此使用共享 helper 把短期 token
放入 query。浏览器、Dataset、Import profile 与 runtime request 都不能选择 parser、source
root、下载方式或 format ID。

SC 图片来源由 `(inspection_time, wafer_key)` 标识。image-parser 打开 context 时只查询一次
Inspection 并取得精确 `eqp_id`，再从代码拥有的 exact registry 选择 Equipment image entry。
EntryFactory 组合设备固定的 Artifact downloader 与 Artifact parser；多个明确列出的设备 ID
可以注册到同一 factory，空 ID、重复 ID 与未知设备直接失败。设备规则不得由启动配置、文件
扩展名、request 字段或 sniffing 改变。当前 legacy entry 固定使用 500-defect range ZIP 与
`PatchReference` / `PatchDefective` / `PatchDifference` 成员命名。仓库另提供固定
`images(sample_id, role, image_bytes, content_type)` schema 的 SQLite Equipment Entry 示例，
使用 `modernc.org/sqlite v1.55.0` 只读解析缓存文件；它仍须由具体 provider 与明确 `eqp_id`
注册后才启用。仓库不提供 Parquet Equipment Entry。其他设备布局应新增并显式注册 Equipment
Entry，而不是恢复通用 format switch。

Artifact downloader 把 upstream source 描述为稳定 `ArtifactRef(entry_id, source_identity,
revision, kind)` 并将文件或目录流式写入 staging path；Artifact parser 只从本地已发布 artifact
读取目标图片。对象存储 revision 优先使用 VersionId，其次 ETag；两者都没有时，文件可使用
可靠的 source `mtime + size`。目录必须由 provider 给出 generation、manifest revision 或可靠
整体更新时间。下载后的本地 mtime 只用于 eviction，不能作为 source freshness。

image-parser 的统一 Artifact Cache Manager 在下载前获取 target-keyed process singleflight 与
跨进程 advisory lock，并在锁内 recheck；miss 写 sibling temp、校验、fsync 后 atomic rename。
Janitor 删除 final target 前获取同一锁，不计算 staging 或持久 coordination 文件。Display、
Prediction、Training、Export 使用同一个 Manager contract，但拥有独立目录、TTL、容量、
并发预算和 metrics；非服务端入口不拥有 cache manager。

大数据集模式不追求与小数据集完全功能对齐。`file_shard_sparse` 的目标是大规模 ingest、批量预测、稀疏人工修正；不是重建完整 `SampleORM + Label Studio` 流程。

SC Train & Predict 对每个有效标注类别最多选择 1,000 个样本进入训练物化。
选择必须按稳定 sample identity 确定性执行，并在应用 workflow filter 后进行。
超出上限的标注样本不进入训练物化，但仍保留在原始预测范围内，预测结果进入
validation/review pool。前端必须在任一类别超过上限时向用户显示该规则，不能把
1,000 条上限实现为未公开的 runtime 默认值。

SC 当前只注册 `yolo-sc-v1` 算法，不保留 ResNet compatibility 分支。YOLO 输入是
`patch_defective` 与 `patch_template` 两张灰度图：每张独立 resize 到 `128x128`，
再按 channel 顺序叠成 `[2, 128, 128]`，禁止在空间维纵向或横向拼图。训练固定
50 epochs；预测模型 batch 固定 256。Training 继续使用可重放、可 shuffle 的
materialized Parquet/DataLoader，但图片 bytes 通过 Training stream 获取；batch Prediction
不生成图片 Parquet。两条路径都不启动 job-local resolver。Prediction、Training 与含图 Export
各自打开语义独立的
bidirectional gRPC stream；一条 stream 可显式打开多个 Inspection context，每个 sequence
对应一个 sample 及其全部 requested roles。服务可在内部并发下载/解析，但必须在有界 reorder
后严格按 sequence 返回，并在 open acknowledgement 中公布 batch、response bytes 与 active
context 上限。客户端只从第一个未 ack sequence 重发；服务不持久化 session，交付语义为
stateless at-least-once。context 通过显式 close、stream cancellation 或 idle timeout 释放，
不设置总运行时长。不得使用 gRPC gzip，也不得 fallback 到已删除的 subprocess/frame path。

一个 image-parser deployment 同时服务 Display、Prediction、Training、Export。各 lane 内 FIFO
且有独立 semaphore；global weighted round-robin limiter 在共享并发上保证 Display latency、
优先 Prediction throughput，并防止 Training/Export 饥饿。服务只返回原始压缩 bytes 与
content type。图片 decode、灰度转换、resize、channel stack 和 tensor/model batch 属于算法
preprocess：训练由可 shuffle 的 DataLoader 路径执行，预测由 4 个 spawn worker、每 task 64、
最多 8 个预取 task、模型 batch 256 的有界 pool 执行。

SC prediction result export 由用户显式选择 Annotation、Prediction 或 Final Class 作为导出
类别；Annotation 与 Prediction 模式先排除没有对应结果的行，Final Class 使用非零 Annotation，
否则使用 Prediction。可选 Review Sampling 先应用 recursive Extra Filter，再按用户声明顺序
逐条执行 typed rules；每一步只消费上一步输出，不得按 filter/selector/cap 重新分组。之后通过独立
Export image stream 按 512 行有界读取每个保留 sample 的 `patch_defective`，不得伪装成
Prediction 或占用 Display lane。包含图片的 KLARF/ZIP 导出必须返回 ZIP，KLARF 中每个非零
图片引用必须精确对应包内文件；缺图、损坏、未知 content type 或 source format 整体不可用
使整个导出失败，不得静默写成零图片。导出允许以临时文件换取有界内存，但图片 bytes 不得
按 Dataset 总量聚合在进程内存中。

SC v3 Prediction 不生成完整临时图片 Parquet，也不为进度预先 collect/count 全量数据。
它从 Dataset 当前持久化数据以 512 行有界扫描；Collection 按成员的
`(inspection_time, wafer_key)` context 映射，通过 Prediction image stream 批量取
`sample × role` 图片。
预处理固定 4 个 spawn 进程，每个 task 最多 64 条、最多预取 8 个
task；主进程聚合为 256 条模型 batch，prediction 每 5,000 条批量写回，结束时写入实际
processed total。因此内存上界由各批次和队列上限决定，不随 Dataset 总样本数线性增长。
图片缺失、损坏等稳定 item error 只生成该 sample 的 prediction error，其他 sample 继续；
模型加载失败、worker 崩溃、Inspection context/source 整体不可用或 gRPC transport 重试耗尽
使整个任务失败。取消时必须关闭 stream、context、队列与子进程。Collection prediction 仍按源
Dataset 拆分写回。

阻塞性能门槛使用 300,000 samples、每 sample 两张代表性压缩图片，测量 warm Artifact Cache
下 production range-ZIP parser 经公共 Prediction gRPC 到 Python 顺序收包，必须至少达到
3,000 samples/s。fixture 生成、cold source 下载和 decode/fake predictor 分开计时，不能混入
该门槛；基准 request batch 固定使用服务公布上限（当前 512）。

完整 capability matrix 和 SC sparse 路径详见 `docs/architecture/dataset-storage-modes.md`。Smoke 验证使用 `make smoke-tests`。

## 5. Label Studio 与 Prediction

Label Studio 是人工标注界面和临时同步界面，不是平台 prediction 的事实来源。

- 平台 prediction 通过 `DatasetStorageAgg.write_predictions(...)` 按 `storage_mode` 持久化：`db_full` 写入 API DB 的 `platform_predictions`，`file_shard_sparse` 写入 dataset-owned per-job prediction Parquet shards 和 `job_result.json`。Prediction flow 不得绕过 aggregate 直接写 repository、ORM 或对象存储。
- Prediction review 的 provenance 指向平台存储拥有的 prediction identity，不指向 Label Studio prediction id。`db_full` 使用平台 prediction id；`file_shard_sparse` 使用 prediction job、sample 和模型 provenance。
- Prediction collection 同步到 Label Studio 是显式人工操作，不是默认持久化路径。
- `ls_project_url` 等环境相关 URL 按当前配置计算，不作为数据库事实持久化。

`db_full` 数据集默认拥有 Label Studio project 并通过 LS task 承载人工标注流程。若某个 storage mode 不支持 LS，必须写入 capability matrix，不能只在代码里隐式分叉。

## 6. 注册与扩展

扩展点必须通过 registry / descriptor 接入，不允许在页面、router、service 中新增硬编码分支作为主要集成方式。

后端：

- View 使用 `@view` 注册。
- Dataset type 使用 dataset registry 和 per-type adapter 注册。
- 版本化 view contract 是 dataset 与 trainer/predictor 的数据兼容边界。
  每个 view descriptor 同时声明稳定 `view_id`、canonical data-plane contract 和
  schema version；不同版本必须是不同 descriptor，可以同时存在。
- 每个版本化 view 由一个 metadata-only `ViewDefinition` 描述。Definition 同时保存
  `ViewContractRef`、row type import path 和 Arrow schema import path；`@view(id=...)`
  只绑定 catalog ID，不允许在 row class 再复制 name、annotation flag 或 contract。
  Data-plane schema registry 从 definition 构建，不维护第二份 view-to-schema map。
- Trainer/predictor 通过 module-owned `RuntimeRouter` decorator 注册。每个
  注册项在同一处声明 metadata、executable callable 和 `algo_id`/版本；中心
  `RuntimeCapabilityCatalog` 只聚合这些 router 并校验 ID 唯一性、view/model
  contract 与 trainer/predictor 配对。
  不再保留 metadata-only trainer/predictor catalog、第二份 executable registry、
  `trainer = register_trainer` / `predictor = register_predictor` 全局别名或目录扫描。
- Paired algorithm class 通过 runtime-checkable `Trainable`、`Predictable` 和
  `TrainAndPredictable` Protocol 声明能力。注册 decorator 在 import 时解析并缓存
  callable；操作支持情况由类实际实现的方法决定，不再通过 route 中的 operation
  字段重复声明。Runtime Protocol 负责成员存在性检查，完整签名由 pyright 校验。
- 被注册的算法函数拥有自己的 dataset construction、view projection、
  materialization/loading、prediction chunk/batch、输出构造和错误语义。
  平台不设置中心 materializer registry，不按 view + purpose + storage mode 为
  所有算法统一选择，也不强制统一的 train/predict 输入输出 DTO。
  通用 runtime context 只传递 job/dataset/model/org identity、请求选项与可用的
  平台上下文；具体 module 再选择 storage/domain/data-plane port。
- API-local compatibility runtime 按算法组织 module，而不是按 operation 组织：同一
  算法的 train 与 predict 必须放在同一 module。禁止恢复独立的 `trainers.py` /
  `predictors.py` 分层，也禁止用 callable 参数或行为 flag 把多种算法塞进同一个通用
  train/predict runner。跨算法共享只限 data-source、artifact/prediction persistence
  等平台 I/O 边界；dataset 准备、workspace 生命周期与模型调用留在算法 module。
- Trainer 必须显式声明一个或多个配对 predictor。Train-and-predict 在只有一个配对
  predictor 时可以确定性解析；存在多个配对项时必须由请求显式选择，禁止根据同名
  ID、目录名或模型名猜测。
- Trainer 必须声明产出的 `ModelContractRef`，predictor 必须声明接受的
  `ModelContractRef`。配对关系同时要求 view contract 和 model contract 精确匹配；
  训练产物必须持久化 model contract/version，预测提交时必须验证，不能只凭
  `trainer_id` 推断模型可加载。
- `RuntimeRouter` 注册项是 API 侧 capability 查询、兼容性校验和本地
  compatibility execution 的共同来源。注册模块可以被 API 进程导入，
  但不得在 import 时加载 Torch/CUDA/模型权重；重依赖位于 `libs/ml`
  或 external runtime，并在被选中的 callable 内延迟 import。
- Prefect deployment 是执行基础设施，不是 capability metadata。Repository-owned
  `PrefectDeploymentSpec` 直接声明 deployment name、flow entrypoint 和 work pool；
  seed、startup validation 与 submission 必须消费同一规格表，禁止从 algorithm
  registration 反向推导 deployment 或根据 resource profile 拼接 work pool 名称。
  Deployment 表示一个 flow 的可提交部署实例，work pool 表示承接执行的资源队列。
- 当前 training、train-and-predict 和 prediction deployment 均由 repository 拥有并
  绑定 `default-gpu`；sensor/drain deployment 绑定 `default-cpu`。当前没有 external
  owner 分支。未来调用外部 runtime 时，优先由一个明确部署的 adapter task/service
  client 包装，不提前把 owner 或外部 entrypoint 写入 capability registration。
- Registered callable 返回 typed async event stream。闭合 `RuntimeEvent` 联合包含
  artifact、metric、progress、recoverable issue 和唯一 terminal completion；Prefect
  flow 以穷尽 match 消费事件并组装 transport-safe result。算法仍拥有自身 dataset、
  workspace、artifact payload/metadata 构造、prediction persistence 与错误语义；
  artifact event sink 负责大文件上传和平台 artifact record 幂等持久化。算法必须在
  创建 payload 的 workspace 仍存活时 yield `ArtifactOutput`，直接事件消费者完成
  上传后才能恢复生成器并清理临时文件。checkpoint 不得以大 bytes 进入 Prefect
  terminal result。可恢复问题 yield issue，预期致命错误抛
  `RuntimeExecutionError`，未知异常直接冒泡。禁止恢复字符串 `output_contract`
  校验或通用 `Ok`/`Err` result chain。
- SC 组合 Train & Predict 在同一个 GPU Prefect flow 中显式运行 module-owned
  `sc-train` 与 `sc-predict` 两个 task。flow-owned workspace 持有本地 checkpoint；训练
  task 返回轻量本地引用后，checkpoint 上传通过 `asyncio.create_task` 与预测 task
  并行，预测直接读取同一文件，不得为组合操作从对象存储重新下载。flow 在清理
  workspace 前必须收拢上传 task；Prefect terminal result 仍只包含持久化后的 artifact
  metadata，不包含 checkpoint bytes 或本地路径。独立训练/独立预测继续使用标准
  artifact event sink 和对象存储边界。
- Missing-image 行为由具体 registered callable 实现，不是 registration 或 runtime
  context 字段。当前 SC trainer 固定跳过不可用图片，并在过滤后不足两个有效类别时
  明确失败；SC predictor 按样本记录失败并继续批处理。
- Training/prediction job dispatch 根据 catalog id 完成数据和模型 contract 校验，再
  向对应的直接 Prefect deployment 提交仅包含 job/source/model/capability identity 与
  请求选项的参数。Prefect wrapper 构建 runtime context、调用类型化 catalog 方法并
  消费事件，不重复传递或校验 catalog id、view/model contract、algorithm version、
  deployment owner 或 resource profile。
  如某算法需要 `@task`/`@flow`，它们必须在被注册函数内显式定义/调用
  或与该函数同 module 声明。禁止恢复通用 `predict-chunk`、通用
  materialize task 或中心 train-and-predict 步骤编排。
  不要保留 `container.gpu_worker` 这类过期执行入口，也不要在通用 API
  route/service 中硬连某个具体 ML 实现作为扩展机制。
- **Mapper** 使用全局 `MapperRegistry`（`app.core.mapper_registry.mapper`）注册类型间转换函数。`@mapper.register(from_types, to_types)` 接受 type 或 ClassVar 字符串，注册笛卡尔积 key。调用方通过 `mapper.get_mapper(src, dst)` 获取转换函数，不再调用 model 类上的 `from_sample` / `to_sample` / `get_adapter` / `as_*` 方法。每个 module 的 mapper 统一放在 `<module>/domain/mapper.py`，由 `app/registrations.py` 触发注册副作用。Mapper 函数必须包含完整转换逻辑，不允许在 model 类上保留内联转换方法；model 类只保留字段定义和 ClassVar 标识。

前端：

- Dashboard widget、importer、exporter、preview launcher、agent skill 通过 descriptor 定义。
- Descriptor 由 app 级 registration barrel 注册到 `widgetRegistry`。
- 业务页面消费 registry 查询结果，不写死组件枚举和 switch-case。

## 7. OpenAPI 与代码生成

前后端 transport contract 由后端 API route/schema DTO 代码导出到 `openapi/openapi.yaml`。`openapi/openapi.yaml` 是生成产物和跨语言消费的 transport contract 快照，不手写维护。

修改 API 请求/响应结构时：

1. 先修改后端 route/schema DTO 代码与实现。
2. 运行 `make generate` 或相关窄生成目标，重新导出 `openapi/openapi.yaml` 并生成后端 transport model、前端类型、Orval/SSE/proto 等 artifact。
3. 再更新前端调用点与 UI-only 类型。
4. 最后运行后端测试与 OpenAPI sync check。

不允许在后端 schema 文件或前端 types 文件中重复手写已经存在于 OpenAPI 的 DTO/type。内部 helper model 或纯 UI model 可以手写。

## 8. 配置与环境

运行行为必须由配置 profile 决定，不允许在业务代码中硬编码环境分支。

- `test` profile 只用于单元/集成测试，可以使用 SQLite、memory storage、mock 外部服务；不得作为可部署测试环境。
- `pre-release` 是可部署的测试/验收环境，必须与 `prod` 使用相同的 Postgres、S3-compatible object storage、后台编排系统和 out-of-process runtime service 边界。
- `dev` / `pre-release` / `prod` profile 面向 Postgres、S3-compatible object storage、后台编排系统和 out-of-process runtime services。
- 未知 profile 必须启动失败；`pre-release` / `prod` 的数据库、公开 URL、凭据和签名 secret 必须由部署环境显式提供，不得继承本地 placeholder。
- Smoke fallback 只能用于本地验证，不得被当作 dev/prod 可靠行为。

如果某个能力在 test/smoke 下被 mock 或降级，必须在测试、文档或 capability matrix 中说明。

Production Compose 默认不发布 Label Studio、Prefect UI、MinIO Console 或其他内部服务
host port。需要访问时由 operator 通过 TLS、认证反向代理或 VPN 显式暴露。Label Studio
在支持它的 Dataset 上作为上下文 work surface；未配置外部 URL 时显示带原因的 disabled
action。Prefect UI 与 MinIO Console 是 operator console，只进入受保护的
`Admin > Infrastructure`；Source connectors 与 Label Studio 配置进入
`Admin > Connections`。前端不得合成 localhost/container URL。

## 9. 数据库与持久化

修改 ORM schema 必须同时提供 Alembic migration。

不允许通过删除 migration 文件绕过启动或迁移错误。若 migration 历史和 compose 数据库状态不一致，应重置数据库或修复 migration 历史，而不是静默跳过。

数据库中持久化的是业务事实。环境相关、可计算、可从配置派生的字段不应该持久化。

## 10. Auth 与组织上下文

后端 route 是否真正受保护必须以当前实现为准，不能因为存在 auth scaffold 就假设所有 route 已经安全。

API、SC data provider 与 image-parser 在 dev、test、pre-release、prod 全部 profile 中始终启用认证；不得提供 auth-disabled profile、隐式开发身份或前端免登录构建开关。公开注册、登录与 OAuth callback 只能通过显式 public router 暴露。

前端 auth state 必须在 route view mount 前完成同步 hydration，避免页面首屏请求先发出后再读取 token，导致错误 `401` 并清空有效 session。

JWT 有过期语义。前端应按 token 的 `exp` 判断当前 session 是否仍有效，不应使用固定前端超时覆盖后端配置。

涉及组织隔离的接口必须显式传递或解析 org context，不允许使用隐式全局默认值绕过权限边界。

## 11. Agent 与 Widget Surface

Agent 对 UI 的控制通过 display surface 和 panel descriptor 表达，不直接操作 Vue component instance。

- Agent chat 使用 `POST -> SSE response stream`。
- SSE event 可以携带文本消息、agent action、sidebar/panel update、done 等事件。
- Surface state 是运行时显示状态，不是业务事实；如需长期保存，必须显式设计 export/import 或落库。
- Widget 之间的交互通过 typed intent 和 shared interaction state 表达，不新增 ad-hoc event bus。

Widget 必须声明自身 contract，包括 props、读取的 shared context、可能发出的 intent 和最小 self-test。没有稳定 row id 的 table/list widget 只能作为展示组件，不能参与跨 widget selection/filter 联动。

## 12. 前端设计

前端采用 Vue 3 + Vite + Naive UI。

页面布局偏好填充整页并避免无意义 overflow。

Dataset 与 Collection 的主导航统一为 `Library` / `数据资源库`，canonical route 为
`/library`。页面使用独立 Datasets/Collections tab，默认 Datasets；tab 与基础
search/creator/current-user scope 写入 URL 并跨 tab 保留，resource-specific filter 与
pagination 独立。旧 `/datasets`、`/dataset-collections` 列表 route 跳转到对应 tab，
详情 route 保持 resource-specific。Create 菜单提供 Import Dataset 与 Create Collection。

迭代页面视觉方案时，每个 PageView 应保留旁路的 `*.design.vue` 页面设计契约文件。设计契约只表达比例、层级、视觉结构，不接真实 API、store 或 router；先更新设计契约，再改真实 PageView。生产代码不得路由或导入设计契约。

## 13. 验证标准

提交代码前应尽量达到：

- 静态检查通过：Python 使用 ruff + pyright；前端使用 TypeScript/Vite 构建检查。
- 后端测试和 OpenAPI sync check 通过。
- 前端 unit/widget 测试通过；涉及用户流程时 E2E 通过。
- 相关 build、storybook、mock、smoke 能力未被破坏。
- 如果删除测试，必须在同一变更中说明删除对象和原因。

不要停在“修坏了”的中间态。若某项检查无法运行，必须明确说明原因和剩余风险。
