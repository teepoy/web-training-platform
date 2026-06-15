# 核心设计

本文是项目的核心设计决议记录。其他文档、`AGENTS.md`、README、代码注释或既有实现与本文冲突时，必须先暴露冲突，并修正文档或取得新的设计决议。

本文可以在同一未提交变更中被修订；这不算偷偷修改。提交前必须让用户看到 `CORE_DESIGNS.md` 的完整 diff，并说明哪些旧决议被覆盖、收窄或废弃。未经用户明确要求，不允许提交本文修改。

## 1. 系统边界

平台分为四个主要运行层：

| 层 | 包 | 职责 | 禁止事项 |
| --- | --- | --- | --- |
| Control plane | `apps/api` | HTTP API、权限、业务参数校验、catalog metadata、任务创建、状态与结果持久化、Prefect flow 定义与部署注册 | API route 不执行训练/预测 callable；API 进程不依赖 Torch/CUDA runtime |
| ML library | `libs/ml` | 模型结构、训练循环、预测逻辑、Torch 数据处理 | 不依赖 API、Prefect、DB ORM、FastAPI router |
| Shared runtime | `libs/platform-runtime` | 跨进程 contracts、DTO、Protocol、SDK/CLI、runtime client | 不反向依赖 `apps/*` |

### Prefect 双池架构

平台使用两个 Prefect work pool 隔离 CPU 与 GPU 负载：

| Pool | Compose 服务 | Profile | 典型负载 |
|------|-------------|---------|----------|
| `default-cpu` | `prefect-worker-cpu` | 默认 | 后台/大批量 import、timer_sensor、dataset_size_sensor、drain_dataset |
| `default-gpu` | `prefect-worker-gpu` | `gpu` | train_job、predict_job、embed_flow |

- 所有 Prefect flow 定义位于 `apps/api/app/modules/*/flows/`。
- `prefect-worker-gpu` 容器通过 `apps/api[gpu]` 可选依赖安装 torch、torchvision、finetune-ml。
- 根 `pyproject.toml` 中 `ruff.flake8-tidy-imports.banned-module-level-imports = ["torch", "tensorflow"]` 禁止 API 进程模块级导入 torch；`libs/ml` 豁免此规则（`per-file-ignores`）。
- Flow 部署注册通过 `ftapi deployments apply` + 一次性 `deployments-bootstrap` compose 服务完成。该服务在启动时创建 `default-cpu` / `default-gpu` 两个 work pool 并注册所有 flow 到对应池。
- 宿主机 GPU worker 可通过 `make prefect-worker-gpu-host` 启动，不可与 compose `--profile gpu` 同时运行。

目标执行拓扑：

```text
apps/api
  -> Prefect server（in-app flow 定义 + ftapi deployments apply）
  -> libs/ml（仅 GPU worker 导入）

apps/api -> libs/platform-runtime

prefect-worker-cpu  -> Prefect server（拉取 default-cpu 池 flow）
prefect-worker-gpu  -> Prefect server（拉取 default-gpu 池 flow）
                    -> libs/ml（GPU 计算）
```

> **迁移说明：** 旧版独立的 `gpu-worker` / `inference` / `embedding` 服务已并入 `apps/api` Prefect flow。原 `apps/worker`、`apps/inference`、`apps/embedding` 目录已移除。

## 2. 后端组织

后端按 DDD / 模块边界组织。

- Route handler 保持薄层，只做协议解析、依赖注入和错误映射。
- 业务逻辑进入 module service；持久化进入 repository。
- 共享基础设施只包含 DB engine/session、对象存储、外部 client 等 infra，不承载模块私有 service/repository。
- 模块间依赖通过显式 Protocol/port，不直接读取 sibling module 内部对象。
- Registration 是模块边界的例外，只允许触发注册副作用或导出 descriptor，不允许借 registration 调用 sibling module 业务逻辑。
- Module domain model 归属所在 module，例如 `apps/api/app/modules/sc`。`libs/platform-runtime` 只承载跨进程 shared contracts，不承载 SC 这类 module 私有 domain model。

API 可以通过 Prefect client 创建 flow run、查询状态、读取日志摘要。Prefect flow 定义可以 co-locate 在 `apps/api/app/modules/*/.../flows/`，但 API route 不启动 flow worker，也不直接执行可训练/可预测 callable。

## 3. Runtime 与任务状态

Prefect 是后台流程编排事实来源。API 是产品业务状态事实来源。前端只通过平台 API 查询任务，不直接消费 Prefect REST payload。

长任务状态边界：

- API 创建平台任务，校验权限和参数，持久化业务状态。
- CPU Worker（`prefect-worker-cpu`）从 `default-cpu` 池拉取 flow，执行后台/大批量导入、传感器、数据导出等 CPU 负载。
- 低延迟、小批量导入可以由 API service 受限执行，但必须显式设置样本数、超时、并发和资源保护边界；route handler 仍保持薄层，不直接承载导入实现。
- GPU Worker（`prefect-worker-gpu`）从 `default-gpu` 池拉取 flow，导入 libs/ml 直接执行训练/预测/嵌入等 GPU 计算。
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

`DatasetStorageAgg.list_samples(return_lazyframe=True, ...)` 是 worker/runtime 批量读的标准表面。`with_labels=True` 由 storage 聚合层把最新标注并入 LazyFrame；trainer/predictor 只消费 LazyFrame，不请求 HTTP materialization，不读 `SampleORM` 逐行 fallback，也不依赖旧 runtime materialization artifact。View/domain projection 属于 trainer/predictor 或 domain aggregate，不属于 storage 层。

`DatasetAgg` 是 domain-specific 聚合层：它包装一个 `DatasetStorageAgg`，承载 SC 等业务语义（如 wafer point 计算、`defect_id` 批量标注、domain 预测编排），但不拥有物理存储、manifest、Parquet shard 或通用 annotation/prediction persistence 细节。新的 domain 能力应优先放在对应 `DatasetAgg`，不是塞进通用 storage Protocol，也不是在 route/service 中新增 hardcoded switch。

SC import 的标准 worker 路径是 `upstream.stream(...)` → domain row normalization → `DatasetStorageAgg.write_samples(...)`。小批量 direct import 是显式低延迟能力，可以保留，但只能作为受限 import 优化；它不能成为训练/预测/导出读取 fallback，也不能重新引入旧 SampleAccess/RuntimeMaterializer 层。Smoke 若要验证 worker path，应显式强制 Prefect flow。

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
- API 侧 trainer/predictor registry 是 metadata catalog，用于列表展示、参数 schema、权限与兼容性校验。
- Worker/inference 侧 runtime registry 才能持有 executable callable。
- API catalog registry 与 runtime executable registry 不允许混用。
- Prediction/training flow 调用 executable registry 解析出的 callable。不要保留 `container.gpu_worker` 这类过期执行入口，也不要在 flow 中硬连某个具体 ML 实现作为扩展机制。
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

- `test` profile 只用于测试，可以使用 SQLite、memory storage、mock 外部服务。
- `dev` / `prod` profile 面向 Postgres、S3-compatible object storage、Prefect、worker runtime 和 inference runtime。
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
