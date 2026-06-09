# SC Import Hybrid Strategy — Direct + Prefect

## TL;DR

> **Quick Summary**: 将 SC Import 从小数据 Direct/大数据 Prefect 的二选一模式改为 Hybrid 模式——前 30,000 行同步 Direct Import（API 进程内），剩余数据异步 Prefect Flow 续传，避免大数据的 API 超时风险同时保持首批数据的低延迟可见。
>
> **Deliverables**:
> - `ScUpstreamReader.stream()` 新增 `offset` 参数跳过已导入行
> - `SqliteScUpstream` 实现 offset 支持
> - `ScImportService.submit_import()` 新增 Hybrid 分支（Direct 30k → Prefect 续传）
> - Prefect flow `sc_import()` 支持 offset + manifest 追加模式
> - TDD 测试覆盖：Hybrid 分支、边界值（30k/30k+1）、manifest 完整性
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Task 1 → Task 5 → Task 6 → Task 8

---

## Context

### Original Request
用户要求：SC Import 遇到大数据集（> 30k 行或 max_rows 未指定）时，先用 Direct Import 同步导入前 30,000 行，剩余部分再走 Prefect Flow 异步导入。

当前逻辑是二选一：`max_rows ≤ 30,000` 全量 Direct，`max_rows > 30,000` 或 `max_rows=None` 全量 Prefect。新的 Hybrid 策略使得首批 30k 行可以低延迟可见，剩余部分不受 API 超时限制。

### Interview Summary
**Key Discussions**:
- **max_rows=None**：尝试 Hybrid（Direct 最多 30k；若上游不足 30k 则 Direct-only 完成，若正好导入 30k 则 Prefect 续传剩余）
- **force_prefect_flow=True**：保持原逻辑，绕过 Hybrid 全部走 Prefect
- **存储模式**：仅 `file_shard_sparse`（db_full 不在范围内）
- **测试策略**：TDD（RED-GREEN-REFACTOR）

**Research Findings**:
- 唯一真实上游实现：`SqliteScUpstream`（SQLite 后端）
- 测试中有两个 mock upstream：`_MockUpstream`（空流）、`FakeUpstream`（3 样本 PatchSample 流）
- Direct import 直接使用 `SparseImportOperator`；Prefect flow 使用 `storage.write_samples()`
- 两个路径都是全量写入（shard_index 从 0 开始，manifest 全新构建）

### Metis Review
**Identified Gaps** (addressed):
- **max_rows ≤ 30k 互动**：明确保持 Direct-only（Hybrid 仅当 max_rows > 30k 或 None 时触发）
- **恰好 30,000 行**：`max_rows=30000` 保持 Direct-only；`max_rows=None` 且首段 Direct 导入 30000 时提交 Prefect，Prefect 流优雅处理 0 行情况
- **max_rows 传递**：Prefect 流收到 `original_max_rows - 30000`（若指定了 max_rows）
- **Manifest 合并策略**：Prefect 流仍通过 `DatasetStorageAgg.write_samples(...)` 写入；`SparseDatasetStorage.write_samples()` 在存储层读取已有 manifest → 以 `len(manifest.shards)` 为起始 shard_index 追加 → 合并后 finalize（不改公共 Protocol）
- **上游数据可变性**：记录为已知限制（Phase 间数据不一致可能导致重复/遗漏）
- **性能假设**：Direct import 30k 行阈值已验证可用（当前已有此上限）

---

## Work Objectives

### Core Objective
SC Import 在遇到 > 30k 行大数据时，先同步 Direct 导入前 30k 行并立即可见，剩余部分提交 Prefect Flow 异步续传，避免大数据长超时同时保持首批低延迟。

### Concrete Deliverables
- `apps/api/app/modules/sc/domain/upstream_reader.py` — Protocol 添加 `offset: int = 0`
- `apps/api/app/modules/sc/adapter/_wafer_mock/sqlite_upstream.py` — 实现 offset
- `apps/api/app/modules/sc/app/services/sc_import_service.py` — Hybrid 分支
- `apps/api/app/modules/sc/adapter/flows/sc_import.py` — offset parameter + pass-through to upstream
- `apps/api/app/modules/datasets/adapter/sparse_storage.py` — append-aware `write_samples()` manifest merge
- 测试文件更新：`test_sc_import_service.py`、`test_sc_import_flow.py`、`test_sc_import_sparse_bytes.py`

### Definition of Done
- [ ] `pytest apps/api/app/modules/sc/tests/ -v` → 全部 PASS（包括新 Hybrid 测试）
- [ ] `uv run --directory apps/api pyright .` → 退出码 0
- [ ] 已有 Direct-only 测试不变（`max_rows=5000` 仍全量 Direct）
- [ ] 已有 `force_prefect_flow=True` 测试不变
- [ ] Hybrid：>30k 行 → manifest.total_rows 等于上游总行数，无重复样本

### Must Have
- `stream(offset=N)` 跳过前 N 行，`offset=0` 行为不变
- Hybrid 分支只在 `max_rows > DIRECT_IMPORT_MAX_ROWS` 或 `max_rows=None` 时触发
- Hybrid Direct phase 若导入 `< DIRECT_IMPORT_MAX_ROWS`，说明上游已耗尽，返回 completed 且不提交 Prefect
- Prefect flow 通过 `DatasetStorageAgg.write_samples(...)` 追加到已有 manifest 时 shard_index 连续不冲突
- Append 后 manifest 的 `sample_index` key 集合必须精确等于 Direct+Prefect 样本身份集合，无重复、无遗漏
- 所有已有测试保持不变（回归）

### Hybrid Decision Table

| Case | Direct phase | Prefect submission | Result |
| --- | --- | --- | --- |
| `force_prefect_flow=True` | No | Yes, original `max_rows` and `offset=0` | `running` |
| `max_rows` in `1..30000` | Yes, `max_rows` rows max | No | `completed` |
| `max_rows > 30000`, direct imports `<30000` | Yes, up to exhaustion | No | `completed` |
| `max_rows > 30000`, direct imports `30000` | Yes | Yes, `offset=30000`, `max_rows=max_rows-30000` | `running` |
| `max_rows=None`, direct imports `<30000` | Yes, up to exhaustion | No | `completed` |
| `max_rows=None`, direct imports `30000` | Yes | Yes, `offset=30000`, `max_rows=None` | `running` |

### Must NOT Have (Guardrails)
- **不修改** `DatasetStorageAgg` Protocol 或 `write_samples()` 公共接口
- **不修改** `db_full` 存储模式代码路径
- **不修改** `ScImportStatus` 模型结构（向后兼容）
- **不修改** `force_prefect_flow=True` 的行为（绕过 Hybrid）
- **不修改** ORM schema / Alembic 迁移
- **不引入** 新的依赖或外部库
- **不修改** `BATCH_SIZE`、shard 大小等性能参数
- **不修改** `_build_image_structs` 重复代码（已有技术债，不改）

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — 所有验证由 agent 执行。

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: TDD
- **Framework**: pytest 9.0.2 + pytest-asyncio
- **TDD Flow**: 每个任务 RED（先写失败测试）→ GREEN（最小实现）→ REFACTOR（清理）

### QA Policy
每个任务必须包含 Agent-Executed QA Scenarios。证据保存到 `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`。
- **API/Backend**: Bash (curl + pytest) — 发送请求、断言状态码和响应字段
- **Library/Module**: Bash (pytest) — 导入模块、调用函数、断言输出

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — Protocol + upstream 实现):
├── Task 1: stream() Protocol 添加 offset 参数 [quick]
├── Task 2: SqliteScUpstream 实现 offset [quick]
├── Task 3: 更新 _MockUpstream.stream() 签名 [quick]
└── Task 4: 更新 FakeUpstream.stream() 签名 [quick]

Wave 2 (After Wave 1 — 核心 Hybrid 逻辑):
├── Task 5: ScImportService Hybrid 分支 + Direct import 返回信息 [deep]
└── Task 6: Prefect flow offset + manifest 追加 [deep]

Wave 3 (After Wave 2 — 集成验证):
├── Task 7: Hybrid Service 层集成测试 [deep]
├── Task 8: Hybrid Prefect Flow 集成测试 [deep]
└── Task 9: 边界值测试 + 回归验证 [quick]

Wave FINAL (After ALL tasks):
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA — 运行全部测试 (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)

Critical Path: Task 1 → Task 2 → Task 5 → Task 6 → Task 8 → FINAL
Parallel Speedup: Wave 1 中 Task 1-4 可并行；Wave 2 中 Task 5-6 可并行
Max Concurrent: 4 (Wave 1)
```

---

## TODOs

- [ ] 1. **stream() Protocol 添加 offset 参数**

  **What to do** (TDD — RED first):
  - 在 `ScUpstreamReader.stream()` Protocol 签名中添加 `offset: int = 0` 参数
  - 先写一个测试：验证带 `offset` 参数的对象 duck-types 通过 Protocol 检查
  - 更新 Protocol 的 docstring 说明 offset 语义

  **Must NOT do**:
  - 不修改 Protocol 的其他方法签名
  - 不修改 `AsyncIterator[pl.DataFrame]` 返回类型

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单文件单方法签名改动，Protocol 层无实现逻辑
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 2, 3, 4, 5, 6
  - **Blocked By**: None

  **References**:
  - `apps/api/app/modules/sc/domain/upstream_reader.py:57-65` — `stream()` 方法当前签名和 docstring
  - `apps/api/app/modules/sc/adapter/_wafer_mock/sqlite_upstream.py:68-93` — `SqliteScUpstream.stream()` 实现（下一步需要实现 offset 的目标）
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:109-111` — `_MockUpstream.stream()` 也需要更新的 mock

  **Acceptance Criteria**:
  - [ ] Protocol 签名添加 `offset: int = 0`，所有现有调用（不传 offset）行为不变

  **QA Scenarios**:

  ```
  Scenario: Protocol backward compatibility — offset omitted
    Tool: Bash (pytest + pyright)
    Preconditions: Protocol changed, implementations not yet updated
    Steps:
      1. Run `uv run --directory apps/api pyright apps/api/app/modules/sc/domain/upstream_reader.py`
      2. Assert exit code 0 (no type errors for the Protocol file itself)
    Expected Result: pyright passes on Protocol definition
    Evidence: .sisyphus/evidence/task-1-protocol-typecheck.txt

  Scenario: Protocol defect — offset with wrong type
    Tool: Bash (pytest)
    Preconditions: None
    Steps:
      1. Verify that passing `offset="abc"` (string instead of int) would be caught at type-check time
      2. Assert that the Protocol declares `offset: int = 0` with int annotation
    Expected Result: Protocol has `offset: int = 0` in signature
    Evidence: .sisyphus/evidence/task-1-protocol-sig.txt
  ```

  **Commit**: YES
  - Message: `feat(sc): add offset parameter to ScUpstreamReader.stream() Protocol`
  - Files: `apps/api/app/modules/sc/domain/upstream_reader.py`

- [ ] 2. **SqliteScUpstream 实现 offset 支持**

  **What to do** (TDD — RED first):
  - 先写测试：`test_stream_offset_skips_rows` — 用已知数据的 mock DB，比 offset=0 和 offset=N 两组的输出
  - 实现：在 `stream()` 的 SQL 查询中使用 `lf.slice(offset, None)` 或在 Polars 层做偏移
  - 处理 offset 超出总行数的情况：返回空流

  **Must NOT do**:
  - 不改变 `BATCH_SIZE = 50_000`
  - 不改变返回的 DataFrame 格式
  - 不修改其他方法（`list_samples`、`list_inspections` 等）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单方法改动，纯 Polars slice 操作
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 3, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 5, 6
  - **Blocked By**: Task 1 (Protocol 签名需要先定)

  **References**:
  - `apps/api/app/modules/sc/adapter/_wafer_mock/sqlite_upstream.py:68-93` — `stream()` 当前实现，特别关注 `lf.slice(offset, BATCH_SIZE)` 模式（行 87-91）
  - `apps/api/app/modules/sc/adapter/_wafer_mock/sqlite_upstream.py:12` — `BATCH_SIZE = 50_000`
  - `apps/api/app/modules/sc/tests/test_sqlite_upstream.py` — 已有 upstream 测试（参考 fixture 和断言模式）
  - `apps/api/app/modules/sc/tests/conftest.py:15-20` — `mock_sc_db_path` fixture 用于创建测试 DB

  **Acceptance Criteria**:
  - [ ] `stream(inspection_time, wafer_key, offset=0)` 返回与原行为相同的所有行
  - [ ] `stream(inspection_time, wafer_key, offset=N)` 跳过前 N 行
  - [ ] `stream(inspection_time, wafer_key, offset=999999)`（超出行数）返回空异步迭代器，不报错

  **QA Scenarios**:

  ```
  Scenario: offset=0 returns all rows (backward compat)
    Tool: Bash (pytest)
    Preconditions: Mock SC DB with 10 defect rows
    Steps:
      1. Call stream(inspection_time, wafer_key, offset=0)
      2. Collect all DataFrames and sum row counts
      3. Assert total rows == 10
    Expected Result: 10 rows returned, identical to old behavior
    Evidence: .sisyphus/evidence/task-2-offset-zero.txt

  Scenario: offset=3 skips first 3 rows
    Tool: Bash (pytest)
    Preconditions: Mock SC DB with 10 defect rows, known defect_id ordering
    Steps:
      1. Call stream(inspection_time, wafer_key, offset=3)
      2. Collect first DataFrame, check first row's defect_id
      3. Assert first defect_id == expected 4th row ID (not 1st)
      4. Assert total rows == 7
    Expected Result: 7 rows, starting from original row 4
    Evidence: .sisyphus/evidence/task-2-offset-skip.txt

  Scenario: offset beyond total rows returns empty
    Tool: Bash (pytest)
    Preconditions: Mock SC DB with 10 defect rows
    Steps:
      1. Call stream(inspection_time, wafer_key, offset=999999)
      2. Assert no items yielded (empty async iterator)
    Expected Result: Empty stream, no error
    Evidence: .sisyphus/evidence/task-2-offset-beyond.txt
  ```

  **Commit**: YES
  - Message: `feat(sc): implement offset support in SqliteScUpstream.stream()`
  - Files: `apps/api/app/modules/sc/adapter/_wafer_mock/sqlite_upstream.py`

- [ ] 3. **更新 _MockUpstream.stream() 签名（service 测试用）**

  **What to do** (TDD — RED first):
  - 确认 `_MockUpstream` 在 `test_sc_import_service.py` 中的 `stream()` 方法签名与 Protocol 保持 duck-type 兼容
  - 添加 `offset: int = 0` 参数（默认值保证向后兼容）
  - 验证现有 service 测试仍然全部通过

  **Must NOT do**:
  - 不改变 mock 的返回逻辑（当前是空流）
  - 不添加新的测试 fixture

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单文件单方法签名对齐，无新逻辑
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 4)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5
  - **Blocked By**: Task 1 (Protocol 签名需要先定)

  **References**:
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:109-111` — `_MockUpstream.stream()` 当前空实现
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:65-112` — 完整 `_MockUpstream` 类

  **Acceptance Criteria**:
  - [ ] `stream(source_inspection_time, source_wafer_key, offset=0)` 行为不变（空流）
  - [ ] `pytest apps/api/app/modules/sc/tests/test_sc_import_service.py -v` → 全部 PASS

  **QA Scenarios**:

  ```
  Scenario: Mock upstream accepts offset parameter
    Tool: Bash (pytest)
    Preconditions: None
    Steps:
      1. Run pytest on test_sc_import_service.py
      2. Assert all existing tests pass (no TypeError from missing offset param)
    Expected Result: All tests pass, pyright no new errors
    Evidence: .sisyphus/evidence/task-3-mock-pass.txt
  ```

  **Commit**: YES (grouped with Task 4)
  - Message: `test(sc): update mock upstream stream() signatures for offset param`
  - Files: `apps/api/app/modules/sc/tests/test_sc_import_service.py`

- [ ] 4. **更新 FakeUpstream.stream() 签名（sparse bytes 测试用）**

  **What to do** (TDD — RED first):
  - 在 `test_sc_import_sparse_bytes.py` 的 `FakeUpstream` 类中添加 `offset: int = 0` 参数
  - 可选择增强 FakeUpstream 以支持 offset（跳过前 N 个样本），或保持只接受参数
  - 验证现有 sparse bytes 测试全部通过

  **Must NOT do**:
  - 不改变 `FakeUpstream` 的样本生成逻辑（3 个 PatchSample 对象）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单文件测试 mock 签名对齐
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 1, 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 6
  - **Blocked By**: Task 1 (Protocol 签名需要先定)

  **References**:
  - `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py:376-381` — `FakeUpstream.stream()` 当前实现
  - `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py:332-381` — 完整 `FakeUpstream` 类

  **Acceptance Criteria**:
  - [ ] `stream(source_inspection_time, source_wafer_key)` 行为不变（返回 3 个 PatchSample）
  - [ ] `pytest apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py -v` → 全部 PASS

  **QA Scenarios**:

  ```
  Scenario: FakeUpstream accepts offset parameter
    Tool: Bash (pytest)
    Preconditions: None
    Steps:
      1. Run pytest on test_sc_import_sparse_bytes.py
      2. Assert all existing tests pass
    Expected Result: All tests pass, no TypeError
    Evidence: .sisyphus/evidence/task-4-fake-pass.txt
  ```

  **Commit**: YES (grouped with Task 3)
  - Message: `test(sc): update mock upstream stream() signatures for offset param`
  - Files: `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py`

- [ ] 5. **ScImportService Hybrid 分支**

  **What to do** (TDD — RED first):
  - 先写测试（RED）：
    - `test_hybrid_submit_with_large_max_rows` — `max_rows=50000` 时：返回 status="running" + flow_run_id，且 Direct import 已执行（manifest 中有 30k 行）
    - `test_hybrid_submit_with_max_rows_none` — `max_rows=None` 时：同 Hybrid 行为
    - `test_hybrid_only_when_above_threshold` — `max_rows=5000` 时：不走 Hybrid（仍全量 Direct）
    - `test_force_prefect_bypasses_hybrid` — `force_prefect_flow=True` + `max_rows=None` 时：不走 Hybrid
  - 实现（GREEN）：
    - 修改 `submit_import()` 决策逻辑：
      ```
      if force_prefect_flow → Prefect only (不变)
      elif max_rows is not None and max_rows <= DIRECT_IMPORT_MAX_ROWS → Direct only (不变)
      else → HYBRID:
        1. 创建 dataset
        2. 调用 _run_direct_import(max_rows=DIRECT_IMPORT_MAX_ROWS) 同步导入前 30k
        3. 计算 Prefect max_rows：若原始 max_rows 不为 None → max_rows - 30,000；否则 None
        4. 若 Direct imported_count < 30,000：返回 status="completed" + imported_count，不提交 Prefect
        5. 若 Direct imported_count == 30,000：提交 Prefect flow（带 dataset_id + offset=30,000 + 计算后的 max_rows）
        6. 返回 status="running" + flow_run_id + imported_count=30,000
      ```
  - 重构（REFACTOR）：确认原 Direct-only 和 Prefect-only 路径无 regression

  **Must NOT do**:
  - 不修改 `DIRECT_IMPORT_MAX_ROWS` 常量
  - 不修改 `_run_direct_import()` 现有逻辑（仅调用方式变化）
  - 不修改 `_create_dataset()` 或 `_fail()` 方法
  - 不在 `_run_direct_import` 中判断 Hybrid（保持纯函数）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 核心业务逻辑改动，涉及多个条件分支、状态管理、Prefect 参数传递
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 6 — 两者虽都依赖 Wave 1 但互不依赖)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 7, 8, 9
  - **Blocked By**: Tasks 1, 2, 3 (Protocol 和所有 upstream 实现准备好)

  **References**:
  - `apps/api/app/modules/sc/app/services/sc_import_service.py:229-400` — `submit_import()` 当前逻辑（特别是行 292-296 的大小判断）
  - `apps/api/app/modules/sc/app/services/sc_import_service.py:38` — `DIRECT_IMPORT_MAX_ROWS = 30000`
  - `apps/api/app/modules/sc/app/services/sc_import_service.py:402-502` — `_run_direct_import()` 实现
  - `apps/api/app/modules/sc/app/services/sc_import_service.py:335-399` — Prefect 流提交逻辑
  - `apps/api/app/modules/sc/adapter/flows/sc_import.py:204-215` — Prefect flow 参数签名（需要确认 offset 参数名一致）
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:1-247` — 已有 service 测试（参考 mock 和断言模式）

  **Acceptance Criteria**:
- [ ] `max_rows=50000, storage_mode=file_shard_sparse` 且上游超过 30k → status="running", flow_run_id 存在, 已 Direct 导入 30k
- [ ] `max_rows=None, storage_mode=file_shard_sparse` 且上游超过 30k → status="running", flow_run_id 存在, 已 Direct 导入 30k
- [ ] 上游不足 30k → status="completed", 无 flow_run_id, 不提交 Prefect
  - [ ] `max_rows=5000, storage_mode=file_shard_sparse` → status="completed", 全量 Direct (无 flow_run_id)
  - [ ] `force_prefect_flow=True, max_rows=None` → status="running", 无 Direct import
  - [ ] 提交 Prefect flow 时 `parameters` 包含 `offset=30000` 和正确的 max_rows 值

  **QA Scenarios**:

  ```
  Scenario: Hybrid with max_rows=50000
    Tool: Bash (pytest)
    Preconditions: Mock upstream with >50k rows, mock prefect client accepting parameters
    Steps:
      1. Call service.submit_import(max_rows=50000, force_prefect_flow=False)
      2. Assert status.status == "running"
      3. Assert status.flow_run_id is not None
      4. Assert status.imported_count == 30000 (Direct portion)
      5. Assert prefect_client.create_flow_run was called with parameters containing offset=30000 and max_rows=20000
    Expected Result: Hybrid triggered, Direct 30k done, Prefect submitted with correct remainder
    Failure Indicators: status="completed" (went Direct-only), flow_run_id is None, wrong max_rows passed
    Evidence: .sisyphus/evidence/task-5-hybrid-50k.txt

  Scenario: Direct-only for max_rows=5000 (regression guard)
    Tool: Bash (pytest)
    Preconditions: Mock upstream with >5k rows
    Steps:
      1. Call service.submit_import(max_rows=5000, force_prefect_flow=False)
      2. Assert status.status == "completed"
      3. Assert status.flow_run_id is None
      4. Assert prefect_client.create_flow_run was NOT called
    Expected Result: Direct-only, no Prefect submission
    Evidence: .sisyphus/evidence/task-5-direct-only-5k.txt

  Scenario: force_prefect bypasses hybrid
    Tool: Bash (pytest)
    Preconditions: Mock upstream with >30k rows
    Steps:
      1. Call service.submit_import(max_rows=None, force_prefect_flow=True)
      2. Assert status.status == "running"
      3. Assert status.flow_run_id is not None
      4. Assert no Direct import was performed (imported_count unchanged or 0)
    Expected Result: Prefect-only, no Direct import
    Evidence: .sisyphus/evidence/task-5-force-prefect.txt

  Scenario: Hybrid when max_rows=None
    Tool: Bash (pytest)
    Preconditions: Mock upstream with >30k rows
    Steps:
      1. Call service.submit_import(max_rows=None, force_prefect_flow=False)
      2. Assert status.status == "running"
      3. Assert Direct import performed (30k rows)
      4. Assert Prefect parameters include offset=30000, max_rows=None
    Expected Result: Hybrid triggered, Prefect with max_rows=None
    Evidence: .sisyphus/evidence/task-5-hybrid-none.txt
  ```

  **Commit**: YES
  - Message: `feat(sc): add hybrid import strategy (Direct 30k + Prefect remainder)`
  - Files: `apps/api/app/modules/sc/app/services/sc_import_service.py`

- [ ] 6. **Prefect flow offset + sparse storage manifest append**

  **What to do** (TDD — RED first):
  - 先写测试（RED）：
    - `test_flow_with_offset_appends_to_existing_manifest` — 使用 FakeUpstream（35 行）和 mock payload store，先写入 30 行的初始 manifest，再调用 flow（offset=30），断言 manifest 总计 35 行、shard_index 连续、sample_index key 精确
    - `test_flow_with_offset_zero_behaves_same_as_before` — offset=0 时行为与原来一致
    - `test_flow_with_offset_beyond_total_returns_zero` — offset 超出上游行数时返回 imported_count=0，manifest 不变
  - 实现（GREEN）：
    - 在 `sc_import()` flow 函数签名中添加 `offset: int = 0` 参数
    - 在 `file_shard_sparse` 路径中始终保持 `storage.write_samples()`，不直接操作 `SparseImportOperator`
    - 传递 offset 到 `upstream.stream(source_inspection_time, source_wafer_key, offset=offset)`
    - 在 `SparseDatasetStorage.write_samples()` 内部支持已有 manifest append：
      1. 读取已有 manifest（若不存在则按空 manifest 处理）
      2. 以 `len(existing_manifest.shards)` 作为起始 shard_index
      3. 以 `existing_manifest.sample_index` 为基准合并新 locator
      4. `total_rows = existing_manifest.total_rows + newly_written`
      5. finalize 合并后的 manifest，并 invalidate cache
  - 重构（REFACTOR）：确认代码无重复（可将 manifest 合并逻辑抽为小辅助函数）

  **Must NOT do**:
  - 不修改 `dataset_id=None` 时的 dataset 创建逻辑
  - 不修改 `db_full` 路径（保持原样）
- 不修改 `SparseImportOperator`、`DatasetPayloadStore` 或 `DatasetStorageAgg.write_samples()` 公共接口
  - 不修改 `write_samples()` 的 `DatasetStorageAgg` Protocol

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Prefect flow 改动涉及 manifest 读写、shard 索引管理、状态合并逻辑，需仔细处理
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 5)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 8, 9
  - **Blocked By**: Tasks 1, 2, 4 (Protocol + upstream 实现 + FakeUpstream 更新)

  **References**:
  - `apps/api/app/modules/sc/adapter/flows/sc_import.py:204-371` — 完整 Prefect flow `sc_import()`
  - `apps/api/app/modules/sc/adapter/flows/sc_import.py:286-328` — `file_shard_sparse` 路径（需修改的主要区域）
- `apps/api/app/modules/datasets/adapter/sparse_storage.py:593-650` — `write_samples()` 当前从 shard_index=0 全量 finalize，需要改为存储层 append-aware
  - `apps/api/app/modules/datasets/app/services/sparse_import_operator.py:63-135` — `SparseImportOperator.flush_shard()` 签名和用法
  - `apps/api/app/modules/datasets/app/services/sparse_import_operator.py:141-182` — `SparseImportOperator.finalize_manifest()` 参数
  - `apps/api/app/modules/sc/tests/test_sc_import_flow.py` — 已有 flow 测试（参考 mock 模式）
  - `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py:376-381` — `FakeUpstream` 可提供有限样本用于集成测试

  **Acceptance Criteria**:
  - [ ] `offset=0` 时 flow 行为与原 flow 完全一致（回归）
  - [ ] `offset=30000` + 已有 30k manifest → 新 shards 从 shard_index=30 开始（若 batch_size=1000）
- [ ] 合并后 manifest.sample_index key 集合精确包含所有 Direct+Prefect 行、manifest.total_rows 为 Direct+Prefect 总和
  - [ ] `offset` 超出上游行数时 → `imported_count=0`，不崩溃，manifest 不变

  **QA Scenarios**:

  ```
  Scenario: Flow with offset=0 behaves same as before (regression)
    Tool: Bash (pytest)
    Preconditions: FakeUpstream with 3 rows, mock payload store, no existing manifest
    Steps:
      1. Call sc_import with offset=0, dataset_id=existing, storage_mode=file_shard_sparse
      2. Assert imported_count == 3
      3. Assert manifest.total_rows == 3, manifest.shard_count appropriate
    Expected Result: Identical to old behavior
    Evidence: .sisyphus/evidence/task-6-offset-zero-regression.txt

  Scenario: Flow appends to existing manifest
    Tool: Bash (pytest)
    Preconditions: Existing manifest with 2 rows (1 shard), FakeUpstream with 3 rows starting from row index 2
    Steps:
      1. Pre-populate payload store with manifest (shard_count=1, total_rows=2, 2 sample_index entries)
      2. Call sc_import with offset=2, dataset_id, storage_mode=file_shard_sparse
      3. Read manifest after flow completes
      4. Assert manifest.total_rows == 4 (2 existing + 2 new, since FakeUpstream stream(offset=2) yields 1 row)
    Expected Result: Manifest merged, shard_index values don't collide
    Failure Indicators: manifest total_rows wrong, duplicate sample_index keys, shard_index collision
    Evidence: .sisyphus/evidence/task-6-append-manifest.txt

  Scenario: Flow with offset beyond upstream returns zero
    Tool: Bash (pytest)
    Preconditions: FakeUpstream with 3 rows, existing manifest with 3 rows
    Steps:
      1. Call sc_import with offset=999, dataset_id, storage_mode=file_shard_sparse
      2. Assert imported_count == 0
      3. Assert manifest unchanged (still 3 rows)
    Expected Result: No crash, imported_count=0
    Evidence: .sisyphus/evidence/task-6-offset-beyond.txt
  ```

  **Commit**: YES
  - Message: `feat(sc): support offset + manifest append in sc_import Prefect flow`
  - Files: `apps/api/app/modules/sc/adapter/flows/sc_import.py`

- [ ] 7. **Hybrid Service 层集成测试**

  **What to do** (TDD — RED first):
  - 写集成测试验证端到端 Hybrid 流程（Service 层，含真实 mock upstream）：
    - `test_hybrid_end_to_end_50k_rows` — 用生成 50k+ 行的 mock upstream，验证 Direct 导入 30k + Prefect 提交
    - `test_hybrid_data_exhausted_before_30k` — 上游只有 20k 行时，max_rows=None，应全部 Direct 导入完毕（imported_count=20k，不提交 Prefect）
    - `test_hybrid_exact_30k_rows` — 上游恰好 30k 行时，应提交 Prefect（但 Prefect 流处理 0 行）
  - 确保 pyright 类型检查通过
  - 确保所有已有测试仍然 PASS

  **Must NOT do**:
  - 不添加新 fixture（使用已有 `_MockUpstream`、`_MockPayloadStore` 等）
  - 不修改已有测试

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 集成测试需编排多个 mock 对象，验证多步骤状态变化
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 9)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:1-247` — 已有 service 测试（mock 模式）
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:65-112` — `_MockUpstream`（可扩展以产生可控数量行）
  - `apps/api/app/modules/sc/tests/test_sc_import_service.py:29-57` — `_MockPrefectSuccess` 和 `_MockPrefectFail`

  **Acceptance Criteria**:
  - [ ] 3 个新测试全部 PASS
  - [ ] `pytest apps/api/app/modules/sc/tests/test_sc_import_service.py -v` → 全部 PASS（新增+已有）
  - [ ] `uv run --directory apps/api pyright apps/api/app/modules/sc/tests/test_sc_import_service.py` → 无错误

  **QA Scenarios**:

  ```
  Scenario: End-to-end hybrid with 50k upstream rows
    Tool: Bash (pytest)
    Preconditions: Mock upstream generating 50k+ rows, mock prefect client
    Steps:
      1. Call submit_import(max_rows=None)
      2. Assert status="running", status.imported_count=30000
      3. Verify prefect_client.create_flow_run was called with offset=30000
      4. Verify dataset was created (mock repository.create_dataset was called)
    Expected Result: Direct imported 30k, Prefect submitted for remainder
    Evidence: .sisyphus/evidence/task-7-e2e-50k.txt

  Scenario: Upstream exhausted before 30k threshold
    Tool: Bash (pytest)
    Preconditions: Mock upstream with only 20k rows
    Steps:
      1. Call submit_import(max_rows=None)
      2. Assert status="completed"
      3. Assert status.imported_count=20000
      4. Assert no Prefect flow was submitted
    Expected Result: All rows imported directly, no Prefect
    Evidence: .sisyphus/evidence/task-7-exhausted.txt

  Scenario: Regression — all existing tests still pass
    Tool: Bash (pytest)
    Preconditions: All Wave 1-2 changes applied
    Steps:
      1. Run `pytest apps/api/app/modules/sc/tests/test_sc_import_service.py -v`
      2. Assert all tests PASS (0 failures)
    Expected Result: Full green suite
    Evidence: .sisyphus/evidence/task-7-regression.txt
  ```

  **Commit**: YES
  - Message: `test(sc): add hybrid import integration tests for service layer`
  - Files: `apps/api/app/modules/sc/tests/test_sc_import_service.py`

- [ ] 8. **Hybrid Prefect Flow 集成测试**

  **What to do** (TDD — RED first):
  - 写 flow 层集成测试（使用 FakeUpstream + mock payload store）：
    - `test_hybrid_flow_append_after_direct` — 模拟 Direct 导入后的状态（已有 manifest 30k 行），调用 flow（offset=30000），验证追加
    - `test_hybrid_flow_manifest_integrity` — 验证合并后 manifest 的 shard_index 连续、sample_index 完整、total_rows 正确
    - `test_hybrid_flow_empty_append` — offset 超出上游行数时 manifest 不变
  - 确保 pyright 通过

  **Must NOT do**:
  - 不修改 FakeUpstream 原有逻辑（仅使用更新后的签名）
  - 不添加新的测试依赖

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Flow 层集成测试需要 mock Prefect 上下文、payload store、manifest 状态
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 9)
  - **Parallel Group**: Wave 3
  - **Blocks**: None
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `apps/api/app/modules/sc/tests/test_sc_import_flow.py` — 已有 flow 测试
  - `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py:332-381` — `FakeUpstream`
  - `apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py` — 已有 sparse import 测试模式

  **Acceptance Criteria**:
  - [ ] 3 个新测试全部 PASS
  - [ ] `pytest apps/api/app/modules/sc/tests/test_sc_import_flow.py -v` → 全部 PASS
  - [ ] `pyright` 无类型错误

  **QA Scenarios**:

  ```
  Scenario: Flow appends after simulated direct import
    Tool: Bash (pytest)
    Preconditions: Pre-populated manifest with 30k rows, FakeUpstream generating 5 more rows
    Steps:
      1. Write initial manifest with 30 shards (1000 rows each, shard_index 0-29)
      2. Call sc_import(offset=30000, dataset_id, storage_mode=file_shard_sparse)
      3. Read manifest after flow
      4. Assert total_rows == 30005
      5. Assert new shard_index values start from 30
      6. Assert sample_index keys equal the expected Direct+Prefect sample ids exactly
    Expected Result: 5 new rows appended, shard_index 30+ used
    Evidence: .sisyphus/evidence/task-8-flow-append.txt

  Scenario: Manifest integrity after append
    Tool: Bash (pytest)
    Preconditions: Existing manifest with 2 rows (1 shard), FakeUpstream with 3 rows at offset 2
    Steps:
      1. Call flow with offset=2
      2. Read manifest
      3. Assert len(manifest.sample_index) == manifest.total_rows
      4. Assert sum(s.row_count for s in manifest.shards) == manifest.total_rows
      5. Assert manifest.shards == sorted(manifest.shards, key=lambda s: s.shard_index)
    Expected Result: Manifest self-consistent
    Evidence: .sisyphus/evidence/task-8-manifest-integrity.txt
  ```

  **Commit**: YES
  - Message: `test(sc): add hybrid flow integration tests for manifest append`
  - Files: `apps/api/app/modules/sc/tests/test_sc_import_flow.py`

- [ ] 9. **边界值测试 + 回归验证**

  **What to do** (TDD — RED first):
  - 边界测试：
    - `test_boundary_exact_30k_direct_only` — `max_rows=30000` → 全量 Direct
    - `test_boundary_30k_plus_1_hybrid` — `max_rows=30001` → Direct 30k + Prefect 1
    - `test_offset_zero_backward_compat` — `stream(offset=0)` 与无 offset 调用结果一致
    - `test_offset_exceeds_total_empty` — 所有 upstream 实现的 offset 超界测试
  - 回归验证：
    - 运行整个 SC 测试套件：`pytest apps/api/app/modules/sc/tests/ -v`
    - 运行 `make test-api` 确保无全局 regression
    - 运行 `uv run --directory apps/api pyright .` 确保类型检查通过

  **Must NOT do**:
  - 不修改生产代码（仅测试）
  - 不跳过任何已有测试

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 测试补充 + 回归运行，无生产代码改动
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 7, 8)
  - **Parallel Group**: Wave 3
  - **Blocks**: FINAL Wave
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `apps/api/app/modules/sc/app/services/sc_import_service.py:38` — `DIRECT_IMPORT_MAX_ROWS`
  - `apps/api/app/modules/sc/app/services/sc_import_service.py:292-296` — 阈值判断逻辑
  - `apps/api/app/modules/sc/tests/` — 全部测试文件

  **Acceptance Criteria**:
  - [ ] `max_rows=30000` → 全量 Direct, status="completed", 无 flow_run_id
  - [ ] `max_rows=30001` → Hybrid: status="running", Direct imported 30k, Prefect params 含 offset=30000, max_rows=1
  - [ ] `pytest apps/api/app/modules/sc/tests/ -v` → 全部 PASS (0 failures)
  - [ ] `make test-api` → 退出码 0
  - [ ] `uv run --directory apps/api pyright .` → 退出码 0

  **QA Scenarios**:

  ```
  Scenario: Boundary — exactly 30k max_rows stays Direct-only
    Tool: Bash (pytest)
    Preconditions: Mock upstream with >30k rows
    Steps:
      1. Call submit_import(max_rows=30000)
      2. Assert status == "completed"
      3. Assert no flow_run_id
    Expected Result: Direct-only, not hybrid
    Evidence: .sisyphus/evidence/task-9-boundary-30k.txt

  Scenario: Boundary — 30,001 max_rows triggers hybrid
    Tool: Bash (pytest)
    Preconditions: Mock upstream with >30k rows
    Steps:
      1. Call submit_import(max_rows=30001)
      2. Assert status == "running"
      3. Assert Prefect params include offset=30000, max_rows=1
    Expected Result: Hybrid triggered, exactly 1 row for Prefect
    Evidence: .sisyphus/evidence/task-9-boundary-30k-plus-1.txt

  Scenario: Full SC test suite regression
    Tool: Bash (pytest)
    Preconditions: All Wave 1-3 changes applied
    Steps:
      1. Run `pytest apps/api/app/modules/sc/tests/ -v`
      2. Assert all tests PASS
      3. Run `uv run --directory apps/api pyright .`
      4. Assert exit code 0
    Expected Result: Zero failures, zero type errors
    Evidence: .sisyphus/evidence/task-9-regression.txt
  ```

  **Commit**: YES
  - Message: `test(sc): add boundary tests for hybrid import threshold`
  - Files: `apps/api/app/modules/sc/tests/` (new test file or added to existing)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. Verify each "Must Have": stream() has offset, SqliteScUpstream supports offset, Hybrid branch exists in submit_import(), Prefect flow accepts offset + appends manifest. Check "Must NOT Have": DatasetStorageAgg Protocol unchanged, db_full path untouched, force_prefect_flow bypass preserved. Evidence files exist in .sisyphus/evidence/.
  Output: `Must Have [4/4] | Must NOT Have [N/N] | Tasks [9/9] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `uv run --directory apps/api pyright .` + `ruff check apps/api/app/modules/sc/` + `pytest apps/api/app/modules/sc/tests/ -v`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log/print in prod code, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names.
  Output: `TypeCheck [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration: Hybrid service → Prefect flow chain, manifest integrity after multiple appends. Test edge cases: empty upstream, exactly 30k rows, 30k+1 rows.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Wave | Tasks | Commit Message | Pre-commit |
|------|-------|---------------|------------|
| 1 | 1 | `feat(sc): add offset parameter to ScUpstreamReader.stream() Protocol` | `uv run --directory apps/api pyright apps/api/app/modules/sc/domain/upstream_reader.py` |
| 1 | 2 | `feat(sc): implement offset support in SqliteScUpstream.stream()` | `pytest apps/api/app/modules/sc/tests/test_sqlite_upstream.py -v` |
| 1 | 3, 4 | `test(sc): update mock upstream stream() signatures for offset param` | `pytest apps/api/app/modules/sc/tests/test_sc_import_service.py apps/api/app/modules/sc/tests/test_sc_import_sparse_bytes.py -v` |
| 2 | 5 | `feat(sc): add hybrid import strategy (Direct 30k + Prefect remainder)` | `pytest apps/api/app/modules/sc/tests/test_sc_import_service.py -v` |
| 2 | 6 | `feat(sc): support offset + manifest append in sc_import Prefect flow` | `pytest apps/api/app/modules/sc/tests/test_sc_import_flow.py -v` |
| 3 | 7 | `test(sc): add hybrid import integration tests for service layer` | `pytest apps/api/app/modules/sc/tests/test_sc_import_service.py -v` |
| 3 | 8 | `test(sc): add hybrid flow integration tests for manifest append` | `pytest apps/api/app/modules/sc/tests/test_sc_import_flow.py -v` |
| 3 | 9 | `test(sc): add boundary tests for hybrid import threshold` | `pytest apps/api/app/modules/sc/tests/ -v && uv run --directory apps/api pyright .` |

---

## Success Criteria

### Verification Commands
```bash
# 完整 SC 测试套件
pytest apps/api/app/modules/sc/tests/ -v
# 预期: 全部 PASS（包括已有 + 新增 Hybrid 测试）

# 类型检查
uv run --directory apps/api pyright .
# 预期: 退出码 0

# 全局 API 测试回归
make test-api
# 预期: 退出码 0
```

### Final Checklist
- [ ] `stream(offset=0)` 与原行为完全一致（回归）
- [ ] `stream(offset=N)` 正确跳过前 N 行
- [ ] `max_rows ≤ 30000` → Direct-only（不变）
- [ ] `max_rows > 30000 或 None` → Hybrid（Direct 30k + Prefect）
- [ ] `force_prefect_flow=True` → 全量 Prefect（绕过 Hybrid）
- [ ] Prefect flow 追加 manifest：shard_index 连续、sample_index 合并、total_rows 正确
- [ ] Prefect flow 不绕过 `DatasetStorageAgg.write_samples(...)`
- [ ] 边界值：30k → Direct-only；30k+1 → Hybrid
- [ ] 0 行上游 → 跳过 dataset 创建 + 返回 completed（已有逻辑不变）
- [ ] 上游不足 30k → 全量 Direct + 无 Prefect 提交
- [ ] 所有 "Must NOT Have" 无违反
