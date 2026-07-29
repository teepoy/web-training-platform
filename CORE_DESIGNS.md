# 核心设计

本文是项目的核心设计决议记录。其他文档、`AGENTS.md`、README、代码注释或既有实现与本文冲突时，必须先暴露冲突，并修正文档或取得新的设计决议。

本文可以在同一未提交变更中被修订；这不算偷偷修改。提交前必须让用户看到 `CORE_DESIGNS.md` 的完整 diff，并说明哪些旧决议被覆盖、收窄或废弃。未经用户明确要求，不允许提交本文修改。

## 0. 失败语义与隐式行为

除非用户明确要求，或本文已有设计决议明确要求，否则不允许新增 fallback、隐式 limit、assumption 或 default。缺少配置、能力、参数、数据或设计决议时，应显式报错、暴露冲突或要求新的设计决议，而不是用兜底行为掩盖问题。

确实需要限流、超时、批量大小、并发上限或兼容 fallback 时，必须把它作为显式产品/运行时设计写清楚，并说明触发条件、可观测信号和不满足条件时的失败方式。

## 1. 系统边界

平台分为五个主要运行层：

| 层                   | 包                                                   | 职责                                                                                             | 禁止事项                                                              |
| -------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| Control plane        | `apps/api`                                           | HTTP API、权限、业务参数校验、catalog metadata、任务创建、状态与结果持久化、runtime service 调度 | API route 不执行训练/预测 callable；API 进程不依赖 Torch/CUDA runtime |
| Runtime services     | `services/*`                                         | out-of-process trainer、predictor、image/parser/upstream adapter 等重依赖运行时                  | 不 import `apps/api` 内部 service/repository/ORM/FastAPI router       |
| Data plane interface | API 暴露的窄接口 / manifest / object storage handoff | 向 runtime services 提供 dataset view、artifact、prediction commit、progress report 等稳定边界   | 不暴露 API module 内部对象或把内部 Python service 当 SDK 使用         |

### Runtime Service 边界

训练、预测、嵌入等带 Torch/CUDA/大型图像依赖的执行逻辑属于 out-of-process runtime services，不属于 API 进程。API 只负责 control plane：创建任务、校验权限和参数、将 catalog entry 路由到 Prefect deployment、持久化业务状态、提供前端查询表面。

- API 进程不安装也不导入 Torch/CUDA runtime。
- 当前不保留独立 `libs/ml` 或 shared Python runtime contracts；这些包没有真实跨进程消费者时会制造假边界。API 内部 demo/type implementation 放在 API owning module 内。
- 未来 SDK/runtime service 边界优先使用 OpenAPI、protobuf/gRPC、Arrow schema/manifest 等生成或传输 contract，而不是手写共享 Python DTO 包。
- Runtime service 不 import `apps/api/app/modules/*` 内部 service、repository、ORM model 或 FastAPI dependency。
- API 可以提供 gRPC/HTTP 等窄 data-plane 接口，也可以返回 manifest 与 signed object-store refs 让 runtime 批量读取；大批量图片/Parquet 不应强制走逐行 RPC。
- Job progress、artifact metadata、prediction commit 等通过稳定 transport contract 回写 API，不通过共享内存对象或 API 内部 Python 类。
- API control-plane module 禁止模块级导入 Torch/TensorFlow；仓库内临时
  ML executable 只能位于 `apps/api/app/runtime_compat/ml`，并由 Prefect flow
  在任务执行阶段懒加载。

目标执行拓扑：

```text
apps/api -> data plane interface / object storage manifest
runtime service -> data plane interface / object storage manifest

apps/api 不直接执行 trainer/predictor callable
runtime service 不直接 import apps/api internals
```

### Perspective WebSocket 隔离

Perspective WebSocket 与普通 HTTP API 必须运行在不同进程和不同容器中：

- `app.main:app` 只提供普通 HTTP API，不注册 Perspective WebSocket 路由。
- `app.perspective_main:app` 只提供 `/api/v1/sc/perspective/**/ws`、健康检查与就绪检查。
- `app.perspective_main:app` 必须使用独立的最小 composition root，只装配数据库 session、Redis、SC upstream 与 dataset storage；禁止复用普通 API 的完整 `build_app_context()`。
- Compose 中使用独立的 `perspective-ws` 服务；Kubernetes 中使用独立 Deployment/Service。
- Web 反向代理必须把 Perspective WebSocket 路径定向到独立的 `perspective_ws` upstream，其余 `/api` 请求仍定向到 `api:8000`。
- 生产 Perspective 容器由 Supervisor 管理四个独立 Uvicorn 进程，分别监听 `8001–8004`；禁止使用 Uvicorn `--workers` 拉起多进程。
- Web Nginx 对 `perspective-ws:8001–8004` 使用 `least_conn` 策略分配长连接。进程数量、监听端口和 Nginx upstream 列表必须同步修改，不能隐式缺省或动态失配。
- Perspective 健康检查必须覆盖容器内全部监听端口。Compose 在 60 秒启动宽限后每 10 秒并行探测一次，单次请求 2 秒超时；连续 3 次失败必须由 PID 1 watchdog 强制终止服务进程组并以非零状态退出，再由 restart policy 重启容器。Kubernetes 使用相同的端口覆盖与失败阈值，由 liveness probe 触发 Pod 重启。
- `PERSPECTIVE_WS_MAX_RSS_MB` 只用于本地/开发环境定位 native allocator 异常；真实生产环境不得因 RSS 高水位把存活 worker 标记为 unready 或主动重启，以免切断活跃 WebSocket。生产内存保护应通过容量监控、连接排空和受控滚动替换处理。
- Perspective 仍必须与普通 API worker 分离；Kubernetes 可以在此进程级拓扑之上增加 Pod 副本。

> **迁移说明：** 旧版独立的 `gpu-worker` / `inference` / `embedding` 服务已并入 `apps/api` Prefect flow。原 `apps/worker`、`apps/inference`、`apps/embedding` 目录已移除。

当前仓库内仍需运行的 demo/兼容 ML executable 必须放在
`apps/api/app/runtime_compat/` 隔离区，而不是
`apps/api/app/modules/*` control-plane module。该目录是迁移边界，不是稳定的
API 内部扩展点：

- API startup、catalog、router、service、composition 和 registration barrel
  禁止 import `app.runtime_compat`。
- 只有 Prefect flow entrypoint 可以在已经解析出明确 executable binding 后懒加载
  `app.runtime_compat`；binding 本身只能保存 module path，不能在 control-plane
  import callable。
- `runtime_compat` 可以临时 import 明确列入 allowlist 的 API data-plane/runtime
  contract，但不能被新的 API 业务代码反向依赖。
- Torch、TorchVision、Ultralytics、Transformers 等 ML 依赖只允许从
  `runtime_compat` executable module 内加载；catalog 枚举和 API import 测试必须证明
  不会加载这些包。
- 新的 production trainer/predictor 不得继续加入 `runtime_compat`；应实现为
  `services/*` out-of-process runtime，通过 manifest、OpenAPI/protobuf 和 Prefect
  deployment 接入。

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

后台编排系统是运行时执行状态来源。API 是产品业务状态事实来源。前端只通过平台 API 查询任务，不直接消费 Prefect、service queue、runtime service 的内部 payload。

长任务状态边界：

- API 创建平台任务，校验权限和参数，持久化业务状态，并将任务交给后台编排或 runtime service。
- CPU runtime service / worker 执行后台/大批量导入、传感器、数据导出等 CPU 负载。
- 低延迟、小批量导入可以由 API service 受限执行，但必须显式设置样本数、超时、并发和资源保护边界；route handler 仍保持薄层，不直接承载导入实现。
- GPU runtime service 执行训练、预测、嵌入等 GPU 计算，并通过 data-plane contract 读取 dataset view、提交 prediction/artifact/progress。
- Task Tracker 表达产品视角的任务阶段、完成状态和产物位置。
- Prometheus/Grafana/Loki 是运维观测系统，不是产品任务状态系统。

实时进度面向前端首选 SSE。WebSocket 不是默认方案。

Prometheus label 不允许包含 `job_id`、`dataset_id`、`model_id`、`user_id`、`org_id` 等高基数字段。单任务细节进入 Prefect、Task Tracker 或结构化日志。

## 4. Dataset / View / Storage

Dataset 相关概念分四层，不能混用：

1. `storage_mode`：物理存储方式，例如 `db_full`、`file_shard_sparse`。
2. `dataset_type`：语义类型，例如 classification、detection、vqa。
3. `view contract`：trainer/predictor 实际消费的数据视图。
4. trainer/predictor/model：运行时能力与模型产物。

`storage_mode` 与 `dataset_type` 正交。任何涉及样本枚举、训练、预测、导出、Label Studio 同步的逻辑都必须显式检查 `storage_mode`，不能从 `dataset_type` 推断。

`view contract` 是 dataset 与 runtime 的兼容边界。Trainer/predictor 只声明自己消费的 view，不直接依赖某个 dataset type 的内部存储结构。

Dataset view samples 必须通过 dataset registry / dataset class / adapter 动态投影。不能为每个 view 新增 hardcoded route 作为主要集成方式。

Dataset operator/storage 层拥有 `db_full`、`file_shard_sparse`、Parquet shard、manifest、locator 等持久化细节。SC import 这类 domain ingest 只负责 upstream/domain model 到通用 dataset sample/import stream 的转换，不直接拥有 sparse shard 或 Parquet 写入逻辑。

`DatasetStorageAgg` 是 dataset storage 的唯一聚合入口。调用方通过 `DatasetStorageFactory.open(dataset_id, org_id)` 按 `storage_mode` 打开具体实现，然后使用统一 Protocol 完成样本枚举、批量写入、标注、预测结果、特征、删除和必要的存储级 materialize/as_hf 操作。训练、预测、导出、agent/classify 等批量读路径不得绕过它去直接使用 `SqlRepository`、`SampleAccessFactory`、`DatasetSampleService`、`RuntimeMaterializer` 或 ad-hoc shard reader。

`DatasetStorageAgg.list_samples(return_lazyframe=True, ...)` 是 API 内部 storage 聚合层的批量读标准表面。面向 out-of-process trainer/predictor 时，API/data-plane 应把对应 view 暴露为稳定 transport contract、Parquet/Arrow manifest 或 signed object-store refs；runtime service 不直接 import `DatasetStorageAgg`、`DatasetStorageFactory`、`SampleORM` 或 API repository。`with_labels=True` 由 storage/data-plane 把最新标注并入 view。View/domain projection 属于 trainer/predictor、domain aggregate 或 data-plane adapter，不属于物理 storage 层。

Storage、data-plane、materializer 的主数据路径必须是 bulk/table-first：优先使用 Polars `LazyFrame`，靠近消费端可按需要 materialize 为 `DataFrame` 或 Arrow `Table`。如需额外 schema、capability、manifest metadata，应包装 lazyframe/dataframe/arrow table 或引用其 schema，不得把大数据路径转换成 dataclass/Pydantic row DTO 列表。除非明确证明数据量小且有边界，禁止对样本行做 Python `for` 循环逐行处理；应使用 LazyFrame/DataFrame/Arrow scan、projection、join、batch、streaming writer 等批量操作。Data-plane manifest 的第一版 contract 见 `docs/architecture/data-plane-manifest-contract.md`。

`DatasetAgg` 是 domain-specific 聚合层：它包装一个 `DatasetStorageAgg`，承载 SC 等业务语义（如 wafer point 计算、`defect_id` 批量标注、domain 预测编排），但不拥有物理存储、manifest、Parquet shard 或通用 annotation/prediction persistence 细节。新的 domain 能力应优先放在对应 `DatasetAgg`，不是塞进通用 storage Protocol，也不是在 route/service 中新增 hardcoded switch。

SC Import as Dataset 当前使用 API service 内的 direct sparse import 路径：`upstream.list_samples(...)` → domain row normalization → sparse shard writer / manifest update。SC import 不再注册或依赖 Prefect flow；Prefect CPU worker 仍保留给 sensors、dataset drain 等后台任务。该 direct import 路径不能成为训练/预测/导出读取 fallback，也不能重新引入旧 SampleAccess/RuntimeMaterializer 层。

平台 sample storage identity 与 module domain identity 必须解耦。`Sample.id` 是平台存储身份；SC `defect_id`、`sample_id`、`inspection_time`、`wafer_key` 等是 domain/upstream identity，不应默认写入全局主键。

Dataset image access 必须通过平台后端代理表达。`file_shard_sparse` 中嵌入的图片通过 `/api/v1/samples/{sample_id}/images/{image_id}?dataset_id=...` 读取；对象存储 URI 通过 `/api/v1/images/resolve?uri=...` 读取；SC upstream/mock 图片通过 `/api/v1/sc/images/...` 作为兼容入口。前端 `<img>` / blink table / preview grid 不能携带自定义 header，因此图片 URL 必须显式携带 token 与 org context query 参数。前端不得把 raw image path helper 的返回值直接作为图片源，必须通过共享 authenticated URL helper 或 image adapter 生成最终 URL。

大数据集模式不追求与小数据集完全功能对齐。`file_shard_sparse` 的目标是大规模 ingest、批量预测、稀疏人工修正；不是重建完整 `SampleORM + Label Studio` 流程。

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
- 版本化 view contract 是 materializer 与 trainer/predictor 的唯一数据兼容边界。
  每个 view descriptor 同时声明稳定 `view_id`、canonical data-plane contract 和
  schema version；不同版本必须是不同 descriptor，可以同时存在。
- 每个版本化 view 由一个 metadata-only `ViewDefinition` 描述。Definition 同时保存
  `ViewContractRef`、row type import path 和 Arrow schema import path；`@view(id=...)`
  只绑定 catalog ID，不允许在 row class 再复制 name、annotation flag 或 contract。
  Data-plane schema registry 从 definition 构建，不维护第二份 view-to-schema map。
- View definition、materializer、trainer、predictor metadata 必须通过 module-owned
  `CapabilityBundle` 进入中心 `CapabilityCatalog`。中心 catalog 负责唯一性、版本、
  引用和配对校验，不依赖目录扫描或 import executable 发现能力。
- Materializer 声明自己产生的精确 `ViewContractRef`，以及支持的 purpose、format
  和 storage mode。Trainer/predictor 只声明消费的精确 `ViewContractRef`，不直接
  绑定具体 materializer；调用方按 view + purpose + storage mode 显式选择
  materializer，没有匹配项时失败，不允许换 view fallback。
- Trainer 必须显式声明一个或多个配对 predictor。Train-and-predict 在只有一个配对
  predictor 时可以确定性解析；存在多个配对项时必须由请求显式选择，禁止根据同名
  ID、目录名或模型名猜测。
- Trainer 必须声明产出的 `ModelContractRef`，predictor 必须声明接受的
  `ModelContractRef`。配对关系同时要求 view contract 和 model contract 精确匹配；
  训练产物必须持久化 model contract/version，预测提交时必须验证，不能只凭
  `trainer_id` 推断模型可加载。
- API 侧 trainer/predictor catalog 只保存 metadata，用于列表展示、参数 schema、
  权限与兼容性校验。
- Prefect deployment 是 executable capability 边界。Catalog entry 通过 descriptor/config/DB metadata 路由到对应 deployment。
- Runtime route 必须显式声明 `owner=local_compat|external`。API 只 seed/update
  `local_compat` deployment；`external` deployment 由 runtime service 拥有，API
  只能解析和调用，禁止覆盖其 entrypoint/work pool。
- API catalog 与 Prefect executable deployment 不允许混用；API 不 import executable callable。
- Training/prediction job dispatch 根据 catalog id、数据 contract、资源 profile 和 config-backed routing descriptor 创建 Prefect flow run。第一版 resource profile 只有 `cpu` / `gpu`。不要保留 `container.gpu_worker` 这类过期执行入口，也不要在 API flow/service 中硬连某个具体 ML 实现作为扩展机制。
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

## 9. 数据库与持久化

修改 ORM schema 必须同时提供 Alembic migration。

不允许通过删除 migration 文件绕过启动或迁移错误。若 migration 历史和 compose 数据库状态不一致，应重置数据库或修复 migration 历史，而不是静默跳过。

数据库中持久化的是业务事实。环境相关、可计算、可从配置派生的字段不应该持久化。

## 10. Auth 与组织上下文

后端 route 是否真正受保护必须以当前实现为准，不能因为存在 auth scaffold 就假设所有 route 已经安全。

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

迭代页面视觉方案时，每个 PageView 应保留旁路的 `*.design.vue` 页面设计契约文件。设计契约只表达比例、层级、视觉结构，不接真实 API、store 或 router；先更新设计契约，再改真实 PageView。生产代码不得路由或导入设计契约。

## 13. 验证标准

提交代码前应尽量达到：

- 静态检查通过：Python 使用 ruff + pyright；前端使用 TypeScript/Vite 构建检查。
- 后端测试和 OpenAPI sync check 通过。
- 前端 unit/widget 测试通过；涉及用户流程时 E2E 通过。
- 相关 build、storybook、mock、smoke 能力未被破坏。
- 如果删除测试，必须在同一变更中说明删除对象和原因。

不要停在“修坏了”的中间态。若某项检查无法运行，必须明确说明原因和剩余风险。
