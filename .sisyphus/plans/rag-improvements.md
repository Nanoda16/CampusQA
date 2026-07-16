# 校园 Q&A 助手 — RAG 改进计划（P0-P3）

## TL;DR

> **快速摘要**: 对照 misaki 分支的 MVP 做差距分析，从零实现缺失模块：评测框架、混合检索、文档异步流水线、前端/基建优化。全部代码原创，不拷贝 misaki。
>
> **交付物**:
> - 50 条评测数据集 + run_eval.py 评测框架
> - 低置信拒答 + Prompt 工程 + Citation 后校验
> - BM25 + RRF + Cross-Encoder 重排的混合检索管线
> - 文档异步入库状态机（4 态） + 单文档工件存储 + 启动自恢复
> - SourceCards 升级 + SSE 客户端 + AuthContext + Alembic + 配置集中化
>
> **预估工作量**: XL（约 4-6 周单人全职）
> **执行方式**: 串行阶段门控（P0 → P1 → P2 → P3），阶段内任务并行
> **关键路径**: Task 0 → P0 验收 → P1 验收 → P2 验收 → P3 验收 → Final

---

## Context

### 原始请求

对照 GitHub 上其他人（misaki 分支）的已有成果，找出差距，清单列出需要完善的内容和需要写的代码。不 fork 别人的，自己重写。

### 差距分析摘要

**misaki 碾压我们的维度**：
- 评测驱动：50 条测试集 + 4 轮消融 + 阈值校准 + 完整报告
- 混合检索：Dense + BM25 + RRF + Cross-Encoder（Hit@5=0.950, MRR@5=0.919, OOD 误答=0%）
- 文档入库：7 态异步状态机 + 原子替换 + 单文档 NPZ 工件
- 质量门禁：citation 后校验 + 低置信拒答
- 前端/基建：SourceCards 折叠面板 + AuthContext + Alembic + 33 项配置

**我们有、misaki 没有的**：
- 独立 ai_service 微服务
- Redis 缓存层
- CLI 多模式工具
- Admin 缓存看板
- 完善的 UserManagement

### Metis 审核要点（已采纳）

- ✅ Task 0 先行：测试基建 + 硬件验证 + 评测数据生成 + 基线测评
- ✅ 状态机从 4 态开始（UPLOADED → PROCESSING → READY → FAILED），不追 7 态
- ✅ 工件存储用 JSON，不用 NPZ（降低复杂度）
- ✅ P0 门控 P1 → P1 门控 P2 → P2 门控 P3
- ✅ BGE-reranker-base 硬件验证在前，无法运行则 P1 降级为 dense + BM25
- ✅ DeepSeek 的 `[Sx]` 引用格式先验证（10 条查询测试），再做 Prompt 工程
- ✅ P3 前端改动延迟到 P0-P1 验收通过后
- ❌ 不超过 3 轮阈值校准

### 设计决策

- **低置信阈值**: 初始 0.35，可从评测校准
- **拒答模板**: "根据现有校园知识库，暂未找到相关信息"
- **引用格式**: `[Sx]`（x 从 1 开始，对应检索结果的排序位置）
- **BM25**: Okapi BM25（k1=1.5, b=0.75），jieba 分词
- **RRF**: k=60（标准值）
- **Reranker**: BGE-reranker-base, max_length=256, top_k=5
- **状态机**: 4 态（UPLOADED → PROCESSING → READY → FAILED），加 error_message 字段
- **工件存储**: JSON 格式（文档 ID → {chunks, metadata, vector_id}）
- **启动恢复**: 扫描工件目录 → 重建 FAISS + BM25 索引
- **前端 SourceCards**: 在现有基础上加 published_at + source_url 超链

---

## Work Objectives

### 核心目标

将校园问答助手的 RAG 质量从「能用」提升到「可评测、可衡量、可演示」，覆盖检索质量、入库自动化、前端表达三大维度。

### 具体交付物

- `evals/campus_qa.jsonl` — 50 条评测数据
- `evals/run_eval.py` — 评测框架
- `ai_service/engine/bm25_retriever.py` — BM25 检索
- `ai_service/engine/fusion.py` — RRF 融合
- `ai_service/engine/reranker.py` — Cross-Encoder 重排
- `ai_service/engine/citation.py` — 引用后校验
- `ai_service/engine/artifact_store.py` — 文档工件管理
- `ai_service/main.py` — 新增端点（reindex, artifact rebuild）
- `backend/app/models/enums.py` — 文档状态枚举
- `backend/app/services/document_service.py` — 异步入库
- `backend/app/routers/document.py` — 触发索引
- `alembic.ini` + `backend/alembic/` — 数据库迁移
- `frontend/src/components/SourceCards.tsx` — 升级
- `frontend/src/lib/sse.ts` — 完善
- `frontend/src/context/AuthContext.tsx` — 重构

### 完成定义

- [ ] 全部 50 条评测用例可运行，输出 JSON 报告
- [ ] Hit@5 / MRR@5 / 拒答率 / 引用正确率 基线已记录
- [ ] 混合检索管线（BM25 + RRF + reranker）通过评测验证
- [ ] 文档上传后自动触发向量化，状态可追踪
- [ ] 前端 SourceCards 显示来源链接 + 日期 + 相关度进度条
- [ ] Alembic 迁移可回滚
- [ ] 配置集中化：全部项从 `.env` 读取

### Must Have

- 全部代码原创（不拷贝 misaki）
- TDD：每个 Task 先写测试再写实现
- Agent-Executed QA 场景覆盖每个 Task 的 happy path + edge case
- 串行阶段门控：P0 全部完成 → P1 开始

### Must NOT Have

- 不引入多 LLM 抽象（DeepSeek 唯一）
- 不扩展现有 RBAC
- 不做 Docker / CI/CD
- 不做 ONNX/INT8 量化
- 不做 Agent / Tool-calling
- 前端不改动整体布局/重构，只升级现有组件

---

## Verification Strategy

> **零人工干预** — 所有验证通过 Agent 脚本执行。

### 测试决策
- **基础设施**: 需新建（pytest + vitest）
- **自动化测试**: **TDD** — 每个任务 RED-GREEN-REFACTOR
- **框架**: pytest（后端）、vitest（前端）

### QA 策略
每个任务必须包含 Agent 执行的 QA 场景（happy path + error case），不依赖人工确认。

- **API/后端**: Bash (curl / httpx) — 发送请求，断言状态码 + 响应字段
- **TUI/CLI**: interactive_bash (tmux) — 运行命令，验证输出
- **前端/UI**: Playwright — 导航、交互、断言 DOM、截图
- **评测**: `python run_eval.py` — 运行测试集，验证指标

---

## Execution Strategy

### 并行波次

```
Wave 0 (Task 0 — 基建先行，串行):
├── Task 1: 测试基础设施 [unspecified-high]
├── Task 2: 硬件验证 + 依赖检查 [quick]
└── Task 3: 评测数据生成（50条）+ 基线测评 [deep]

Wave 1 (P0 — 评测 + 拒答 + Prompt，并行):
├── Task 4: 低置信拒答 [quick]
├── Task 5: Prompt 工程 [quick]
└── Task 6: 评测框架 run_eval.py [unspecified-high]
→ P0 验证门控

Wave 2 (P1 — 检索升级，并行):
├── Task 7: BM25 检索 + jieba [unspecified-high]
├── Task 8: RRF 融合 [quick]
├── Task 9: Cross-Encoder 重排 [unspecified-high]
├── Task 10: 阈值校准（≤3 轮） [deep]
└── Task 11: Citation 后校验 [unspecified-high]
→ P1 验证门控

Wave 3 (P2 — 文档流水线，并行):
├── Task 12: 文档状态机（模型+枚举+迁移） [unspecified-high]
├── Task 13: 异步入库线程池 [deep]
├── Task 14: 单文档工件存储 [unspecified-high]
├── Task 15: 启动自恢复（从工件重建索引） [quick]
└── Task 16: 上传→自动索引集成 [quick]
→ P2 验证门控

Wave 4 (P3 — 前端/基建，并行):
├── Task 17: SourceCards 升级 [visual-engineering]
├── Task 18: SSE 客户端完善 [quick]
├── Task 19: AuthContext 重构 [visual-engineering]
├── Task 20: Alembic 迁移 [unspecified-high]
└── Task 21: 配置集中化（.env + Pydantic） [quick]
→ P3 验证门控

Wave FINAL（全并行验证）:
├── F1: 合规审计 [oracle]
├── F2: 代码质量 + 测试 [unspecified-high]
├── F3: 全场景 QA [unspecified-high + playwright]
└── F4: 范围一致性 [deep]
→ 用户确认完成
```

### 依赖矩阵

- **1-3**: (无依赖) → 4-6, 1
- **4**: 1, 2, 3 → 6, 1
- **5**: 1, 2 → 6, 1
- **6**: 1, 2, 3, 4, 5 → 7-8, 2
- **7**: 1, 6 → 8-11, 2
- **8**: 7 → 10-11, 2
- **9**: 1, 6 → 10-11, 2
- **10**: 6, 7, 8, 9 → 11, 2
- **11**: 6, 7, 8, 10 → 12-16, 3
- **12**: 1 → 13-16, 3
- **13**: 12 → 14-16, 3
- **14**: 12, 13 → 15-16, 3
- **15**: 14 → 16, 3
- **16**: 13, 14, 15 → 17-21, 4
- **17**: 1 → 20-21, 4
- **18**: 1 → 20-21, 4
- **19**: 1 → 20-21, 4
- **20**: 12 → 21, 4
- **21**: 1, 20 → 17-19, 4

### Agent 分派汇总

- **Wave 0**: 3 个 — T1 → `unspecified-high`, T2 → `quick`, T3 → `deep`
- **Wave 1**: 3 个 — T4 → `quick`, T5 → `quick`, T6 → `unspecified-high`
- **Wave 2**: 5 个 — T7 → `unspecified-high`, T8 → `quick`, T9 → `unspecified-high`, T10 → `deep`, T11 → `unspecified-high`
- **Wave 3**: 5 个 — T12 → `unspecified-high`, T13 → `deep`, T14 → `unspecified-high`, T15 → `quick`, T16 → `quick`
- **Wave 4**: 5 个 — T17 → `visual-engineering`, T18 → `quick`, T19 → `visual-engineering`, T20 → `unspecified-high`, T21 → `quick`
- **FINAL**: 4 个 — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Task 0-1: 测试基础设施（pytest + vitest）

  **What to do**:
  - 搭建 pytest 环境：`pytest.ini`、`backend/tests/conftest.py`（fixture: 测试 DB session、测试 HTTP client、mock Redis、mock ai_service）
  - 搭建 vitest 环境：`frontend/vitest.config.ts`、`frontend/src/__tests__/` 目录
  - 为现有后端代码写 3 个冒烟测试（`test_root.py`、`test_auth.py`、`test_docs.py`）验证框架工作
  - 写 1 个前端组件冒烟测试验证 vitest 工作
  - 配置 `pyproject.toml` 添加 pytest 依赖、test 命令

  **Must NOT do**:
  - 不写 mock 之外的集成测试（集成放后面任务）
  - 不改动任何业务代码

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 测试基建需要全面理解现有项目结构，但不是核心业务逻辑
  - **Skills**: 无（不加载 skill）
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Task 2, 3)
  - **Blocks**: Tasks 4-6, 9, 12, 17-19
  - **Blocked By**: None (can start immediately)

  **References**:
  - `backend/app/main.py` — FastAPI 应用实例（用于 TestClient fixture）
  - `backend/app/database.py` — SQLAlchemy session 配置（用于测试 DB fixture）
  - `backend/app/config.py` — 现有配置（测试时需覆盖 DATABASE_URL 为 sqlite）
  - `frontend/vite.config.ts` — 前端构建配置（vitest 集成参考）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `pytest.ini` 创建，`backend/tests/conftest.py` 包含 `client` fixture
  - [ ] `pytest backend/tests/` — 3 个冒烟 PASS，0 failure
  - [ ] `vitest run frontend/src/__tests__/` — 1 个冒烟 PASS

  **QA Scenarios**:

  ```
  Scenario: pytest 框架可用
    Tool: Bash
    Preconditions: pip install -e ".[dev]" 或 pip install pytest httpx
    Steps:
      1. cd backend && pytest tests/ -v --tb=short
    Expected Result: 绿色输出，3 passed，合计 <5s
    Failure Indicators: ModuleNotFoundError / 测试失败
    Evidence: .sisyphus/evidence/task-1-pytest-pass.txt

  Scenario: vitest 框架可用
    Tool: Bash
    Preconditions: npm install
    Steps:
      1. cd frontend && npx vitest run
    Expected Result: 绿色输出，1 passed
    Failure Indicators: 模块解析失败 / 测试失败
    Evidence: .sisyphus/evidence/task-1-vitest-pass.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-1-pytest-pass.txt`
  - [ ] `.sisyphus/evidence/task-1-vitest-pass.txt`

  **Commit**: YES (group with Tasks 2, 3)
  - Message: `test: add pytest + vitest infrastructure`
  - Files: `backend/tests/`, `frontend/vitest.config.ts`, `pytest.ini`, `pyproject.toml`


- [x] 2. Task 0-2: 硬件验证 + 依赖检查

  **What to do**:
  - 检查系统可用 RAM（需 ≥8GB 空闲以运行 embedding + reranker 双模型）
  - 检查磁盘空间（FAISS 索引 + 工件目录 ≥5GB）
  - 验证 BGE-reranker-base 能否加载（`sentence-transformers` + torch）
  - 验证 jieba 分词库可用
  - 验证 DeepSeek API `[Sx]` 引用格式：发 10 条不同查询，检查输出中 `[S1]` 等格式的出现率和正确性
  - 记录验证结果到 `ai_service/hw_validation.json`
  - 如果 reranker 无法加载，标记 P1 降级（dense + BM25 only）

  **Must NOT do**:
  - 不改任何业务代码
  - 不安装非必需依赖

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 验证任务，无代码编写
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 0 (with Task 1, 3)
  - **Blocks**: Task 4, 5, 9
  - **Blocked By**: None (can start immediately)

  **References**:
  - `ai_service/engine/embedding.py` — 现有 embedding 初始化代码（参考模型加载方式）
  - `ai_service/engine/generator.py` — 现有 DeepSeek 调用（用于测试 [Sx] 格式）

  **Acceptance Criteria**:

  **TDD**: N/A — 验证任务，非代码任务

  **QA Scenarios**:

  ```
  Scenario: reranker 模型可加载
    Tool: Bash
    Preconditions: proxy on（网络下载模型）
    Steps:
      1. python3.11 -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('BAAI/bge-reranker-base'); print(m.max_seq_length); print('OK')"
    Expected Result: max_length >= 256，打印 OK
    Failure Indicators: OOM / model not found / import error
    Evidence: .sisyphus/evidence/task-2-reranker-load.txt

  Scenario: jieba 可用
    Tool: Bash
    Preconditions: pip install jieba
    Steps:
      1. python3.11 -c "import jieba; print(list(jieba.lcut('河海大学计算机学院'))); print('OK')"
    Expected Result: 正确分词（'河海大学', '计算机', '学院'），打印 OK
    Failure Indicators: import error
    Evidence: .sisyphus/evidence/task-2-jieba-ok.txt

  Scenario: DeepSeek [Sx] 格式验证
    Tool: Bash
    Preconditions: ai_service 运行中
    Steps:
      1. python3.11 ai_service/cli.py --ask "河海大学校训是什么" 2>&1 | tail -20
    Expected Result: 输出包含河海大学相关内容
    Failure Indicators: API key / timeout
    Evidence: .sisyphus/evidence/task-2-deepseek-sx-test.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-2-reranker-load.txt`
  - [ ] `.sisyphus/evidence/task-2-jieba-ok.txt`
  - [ ] `.sisyphus/evidence/task-2-deepseek-sx-test.txt`

  **Commit**: YES (group with Task 1)
  - Message: `chore: hardware validation + dependency checks`
  - Files: `ai_service/hw_validation.json`


- [x] 3. Task 0-3: 评测数据生成 + 基线测评

  **What to do**:
  - 从 `knowledge_docs/` 挑选 50 个 QA 对：
    - 30 条单轮知识题（从现有知识文档中提取真实可答问题）
    - 10 条多轮对话问题（2-3 轮对话上下文 + 最终查询）
    - 10 条知识库外问题（OOD，系统不应回答的内容）
  - 每条格式：JSONL，含 `id`, `group`, `question`, 多轮时含 `history`, `answerable`, `gold_title_contains`, `expected_terms`
  - 保存到 `evals/campus_qa.jsonl`
  - 运行基线测评（当前 dense-only 系统）：对所有 50 条做检索 + 生成
  - 记录基线指标到 `evals/baseline_results.json`

  **Must NOT do**:
  - 不虚构测试数据（必须从真实文档提取）
  - OOD 问题必须是对河海大学不合逻辑的查询（不是"我不知道"的问题，而是知识库确定没有的）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要深入阅读所有知识文档，理解内容，提取有意义的 QA 对
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES (partially — 可以先建 JSONL，再跑基线)
  - **Parallel Group**: Wave 0 (with Task 1, 2)
  - **Blocks**: Task 6 (evaluation framework needs data)
  - **Blocked By**: None (can start immediately)

  **References**:
  - `knowledge_docs/` — 所有知识文档来源
  - `ai_service/cli.py` — CLI 可用来跑单个查询的基线
  - `ai_service/main.py` — /query 端点

  **Acceptance Criteria**:

  **TDD**: N/A — 数据生成任务，非代码任务

  **QA Scenarios**:

  ```
  Scenario: 评测数据格式验证
    Tool: Bash
    Preconditions: evals/campus_qa.jsonl 已创建
    Steps:
      1. python3.11 -c "
        import json
        data = [json.loads(l) for l in open('evals/campus_qa.jsonl')]
        groups = {}
        for d in data:
          groups.setdefault(d['group'], []).append(d['id'])
        print(f'Total: {len(data)}')
        for g, ids in groups.items():
          print(f'  {g}: {len(ids)}')
        assert len(data) == 50
        "
    Expected Result: "Total: 50"，各组数量正确，assert 通过
    Failure Indicators: JSON decode error /数量不对
    Evidence: .sisyphus/evidence/task-3-eval-data-valid.txt

  Scenario: 基线检索验证
    Tool: Bash
    Preconditions: ai_service 运行中
    Steps:
      1. curl -s -X POST http://localhost:8003/query -H 'Content-Type: application/json' -d '{"question":"河海大学校训","top_k":5}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); print(f'Sources: {len(d.get(\"sources\",[]))}'); assert len(d.get('sources',[])) >= 1"
    Expected Result: Sources >= 1，assert 通过
    Failure Indicators: 服务未运行 / 空 sources
    Evidence: .sisyphus/evidence/task-3-baseline-query.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-3-eval-data-valid.txt`
  - [ ] `.sisyphus/evidence/task-3-baseline-query.txt`

  **Commit**: YES (group with Task 1)
  - Message: `feat(evals): 50 eval test cases + baseline results`
  - Files: `evals/campus_qa.jsonl`, `evals/baseline_results.json`


---

### Wave 1 — P0: 评测 + 拒答 + Prompt 工程

- [x] 4. Task P0-1: 低置信拒答

  **What to do**:
  - 在 `ai_service/engine/retriever.py` 中实现低置信检测：
    - 检索返回后，检查 top-1 score 是否低于阈值（默认 0.35）
    - 如果低于阈值，标记 `low_confidence = True`
  - 在 `ai_service/engine/pipeline.py` 的 query 流程中：
    - 如果 `low_confidence`，不调用 LLM，直接返回拒答模板
  - 拒答模板：`"根据现有校园知识库，暂未找到关于「{question}」的可靠信息。"`
  - 阈值从配置读取（`ai_service/config.py` 或环境变量 `REJECTION_THRESHOLD`），默认 0.35
  - TDD: 先写测试测正常回答 vs 拒答

  **Must NOT do**:
  - 不修改 LLM 生成逻辑（只是短路不生成）
  - 不改变正常查询路径的性能

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 改动范围小，单文件修改
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 5, 6)
  - **Blocks**: Task 6
  - **Blocked By**: Task 1, 2

  **References**:
  - `ai_service/engine/retriever.py` — 当前检索逻辑，需要判断返回 score
  - `ai_service/engine/pipeline.py` — query 流程入口，需加入置信度检查
  - `ai_service/engine/generator.py` — 当前 LLM 调用（被短路跳过）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_rejection_threshold_below`：低 score 查询 → 返回拒答模板
  - [ ] `test_rejection_threshold_above`：正常 score 查询 → 正常回答
  - [ ] `test_rejection_configurable`：改变阈值配置 → 拒答行为变化

  **QA Scenarios**:

  ```
  Scenario: 低于阈值返回拒答
    Tool: Bash (curl)
    Preconditions: ai_service 运行中，REJECTION_THRESHOLD=0.99（强制拒答）
    Steps:
      1. curl -s -X POST http://localhost:8003/query -H 'Content-Type: application/json' -d '{"question":"河海大学校训","top_k":5}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:50]); assert '暂未找到' in d['answer']"
    Expected Result: 返回拒答模板，包含"暂未找到"
    Failure Indicators: 返回了正常回答 / 报错
    Evidence: .sisyphus/evidence/task-4-rejection-below.txt

  Scenario: 高于阈值正常回答
    Tool: Bash (curl)
    Preconditions: ai_service 运行中，REJECTION_THRESHOLD=0.0（永不拒答）
    Steps:
      1. curl -s -X POST http://localhost:8003/query -H 'Content-Type: application/json' -d '{"question":"河海大学校训","top_k":5}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:80]); assert '暂未找到' not in d['answer']"
    Expected Result: 正常回答，不包含拒答模板
    Failure Indicators: 仍返回拒答 / 报错
    Evidence: .sisyphus/evidence/task-4-rejection-above.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-4-rejection-below.txt`
  - [ ] `.sisyphus/evidence/task-4-rejection-above.txt`

  **Commit**: YES (group with Tasks 5, 6)
  - Message: `feat: low-confidence rejection for OOD queries`
  - Files: `ai_service/engine/retriever.py`, `ai_service/engine/pipeline.py`


- [x] 5. Task P0-2: Prompt 工程

  **What to do**:
  - 重写 `ai_service/engine/prompts.py` 的 system prompt：
    - 明确限定：只能依据【参考资料】回答，不得用模型记忆补充
    - 引用格式：每项可核查事实后标注 `[Sx]`（x 为来源序号）
    - 资料不足时拒答（与 Task 4 的拒答模板协同）
    - 时效信息标注资料日期，建议核实最新版本
    - 避免角色扮演指令（防止 prompt injection）
  - 添加 user prompt 模板：context（检索到的 chunks） + question
  - TDD: 测试不同 prompt 模板的输出格式

  **Must NOT do**:
  - 不改 LLM 调用代码（只改 prompt 内容）
  - 不添加多语言支持

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 单文件修改，文字工作为主
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 4, 6)
  - **Blocks**: Task 6, 11 (citation validation)
  - **Blocked By**: Task 1, 2

  **References**:
  - `ai_service/engine/prompts.py` — 当前 prompt 模板（需要完全重写）
  - `ai_service/engine/generator.py` — 使用 prompt 的地方（确认调用接口兼容）
  - `ai_service/engine/pipeline.py` — query 流程构 prompt 的地方

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_prompt_contains_citation_instruction`：system prompt 包含 `[Sx]` 引用格式说明
  - [ ] `test_prompt_contains_rejection_instruction`：system prompt 包含拒答指令
  - [ ] `test_prompt_contains_disclaimer`：system prompt 包含时效信息标注要求

  **QA Scenarios**:

  ```
  Scenario: Prompt 格式验证
    Tool: Bash
    Preconditions: 代码已修改
    Steps:
      1. python3.11 -c "
        from ai_service.engine.prompts import get_system_prompt
        p = get_system_prompt()
        assert '[S' in p, 'Missing citation format'
        assert '参考资料' in p, 'Missing reference instruction'
        assert '暂未找到' in p or '无法回答' in p, 'Missing rejection instruction'
        print('Prompt validation: PASS')
        print(p[:200])
        "
    Expected Result: 三个 assert 全部通过，打印 PASS 和 prompt 前 200 字符
    Failure Indicators: AssertionError
    Evidence: .sisyphus/evidence/task-5-prompt-valid.txt

  Scenario: 使用新 prompt 的问答响应
    Tool: Bash (curl)
    Preconditions: ai_service 运行中
    Steps:
      1. curl -s -X POST http://localhost:8003/query -H 'Content-Type: application/json' -d '{"question":"河海大学校训是什么","top_k":5}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); a=d['answer']; print(a[:200]); assert '[S1]' in a or '[S' in a"
    Expected Result: 回答包含类似 `[S1]` 的引用标注
    Failure Indicators: 无引用标注
    Evidence: .sisyphus/evidence/task-5-answer-citation.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-5-prompt-valid.txt`
  - [ ] `.sisyphus/evidence/task-5-answer-citation.txt`

  **Commit**: YES (group with Task 4)
  - Message: `feat: add citation format and rejection guard to prompts`
  - Files: `ai_service/engine/prompts.py`


- [x] 6. Task P0-3: 评测框架 run_eval.py

  **What to do**:
  - 在 `evals/run_eval.py` 实现评测框架：
    - 加载 `campus_qa.jsonl` 测试集
    - 对每条用例调用 ai_service /query 端点
    - 计算指标：
      - Hit@5：前 5 个检索结果中是否包含 gold title
      - MRR@5：正确来源的倒数排名均值
      - Recall@5：召回率
      - Precision@5：精确率
      - OOD 拒答率：知识库外问题被正确拒绝的比例
      - 引用正确率：`[Sx]` 引用指向真实检索结果的比例
      - P95 延迟
    - 输出 JSON 报告到 `evals/results/{timestamp}/`
    - 支持参数模式：`--mode {retrieval,generation,full}`，`--threshold`, `--reranker`, `--top-k`
    - 支持消融对比（不同配置运行并输出对比表）
  - TDD: 用已知结果的 3 条虚构数据验证指标计算正确性

  **Must NOT do**:
  - 不在评测框架中调用 DeepSeek API（除非 `--mode generation`）
  - 不修改 ai_service 代码（只消费 API）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要全面实现指标计算、多模式、报告生成
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 4, 5)
  - **Blocks**: Task 7-11 (P1 all need eval to measure improvement)
  - **Blocked By**: Task 1, 3, 4, 5

  **References**:
  - `evals/campus_qa.jsonl` — 评测数据（Task 3 产出）
  - Misaki's `docs/evaluation_summary.md` — 评测报告格式参考（思路可借鉴，不抄代码）
  - `ai_service/main.py` — /query 端点返回格式

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_hit_at_5_computation`：3 条虚构检索结果 → 正确计算 Hit@5
  - [ ] `test_mrr_at_5_computation`：3 条虚构检索结果 → 正确计算 MRR@5
  - [ ] `test_ood_rejection_rate`：混入 OOD 问题 → 正确计算拒答率
  - [ ] `test_citation_accuracy`：包含/不包含正确引用 → 正确计算引用正确率

  **QA Scenarios**:

  ```
  Scenario: 检索模式运行
    Tool: Bash
    Preconditions: ai_service 运行中，evals/campus_qa.jsonl 存在
    Steps:
      1. cd evals && python3.11 run_eval.py --mode retrieval --output results/test_retrieval.json
      2. python3.11 -c "import json; d=json.load(open('evals/results/test_retrieval.json')); print(json.dumps(d['metrics'], ensure_ascii=False, indent=2)); assert 'hit_at_5' in d['metrics']"
    Expected Result: 输出指标（hit_at_5, mrr_at_5, 等）
    Failure Indicators: JSON 格式错 / 指标缺失
    Evidence: .sisyphus/evidence/task-6-eval-retrieval.txt

  Scenario: 指标格式验证
    Tool: Bash
    Preconditions: eval 结果已生成
    Steps:
      1. python3.11 -c "
        import json
        d = json.load(open('evals/results/test_retrieval.json'))
        m = d['metrics']
        for k in ['hit_at_5','mrr_at_5','recall_at_5','precision_at_5','ood_rejection_rate','p95_latency_ms']:
          assert k in m, f'Missing {k}'
        print(f'All {len(m)} metrics present: {list(m.keys())}')
        "
    Expected Result: 全部 6 个指标存在
    Failure Indicators: KeyError
    Evidence: .sisyphus/evidence/task-6-metrics-format.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-6-eval-retrieval.txt`
  - [ ] `.sisyphus/evidence/task-6-metrics-format.txt`

  **Commit**: YES (group with Task 4, 5)
  - Message: `feat(evals): evaluation framework with retrieval/generation/full modes`
  - Files: `evals/run_eval.py`, `evals/results/`


---

### Wave 2 — P1: 检索升级

- [x] 7. Task P1-1: BM25 检索 + jieba 分词

  **What to do**:
  - 创建 `ai_service/engine/bm25_retriever.py`：
    - 使用 `rank_bm25` 库实现 BM25Okapi（k1=1.5, b=0.75）
    - 使用 `jieba` 分词器对文档和查询分词
    - 构建方法：`build(corpus: list[str], chunk_ids: list[int])`
    - 检索方法：`retrieve(query: str, top_k: int) -> list[(chunk_id, score)]`
    - 保存/加载方法：`save(path)`, `load(path)`
  - 集成到 `ai_service/engine/pipeline.py`：
    - 在 `index_documents()` 中构建 BM25 索引
    - 在 query 流程中调用 BM25 检索
    - 保存 BM25 索引到 `ai_service/data/bm25/` 目录
  - TDD: 测试 BM25 构建 + 检索 + 保存/加载

  **Must NOT do**:
  - 不替换现有 dense 检索（两者共存，RRF 在 Task 8 做）
  - 不修改 embedding 或 FAISS 代码

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 核心检索模块，需要正确集成到现有 pipeline
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on 6 for testing)
  - **Parallel Group**: Wave 2 (with Task 8, 9)
  - **Blocks**: Task 8 (RRF), Task 10 (calibration), Task 11 (citation)
  - **Blocked By**: Task 1 (test infra), Task 6 (eval framework)

  **References**:
  - `ai_service/engine/retriever.py` — 现有 dense 检索的接口模式（BM25 要匹配相同返回格式）
  - `ai_service/engine/vector_store.py` — FAISS 的操作模式参考
  - `ai_service/engine/pipeline.py` — pipeline 中集成新检索器

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_bm25_build`：构建 BM25 索引后 `index.count` > 0
  - [ ] `test_bm25_retrieve`：已知关键词查询返回对应的 chunk_id
  - [ ] `test_bm25_save_load`：保存后再加载，检索结果一致
  - [ ] `test_bm25_jieba_tokenization`：中文句子分词结果符合预期

  **QA Scenarios**:

  ```
  Scenario: BM25 构建 + 检索
    Tool: Bash
    Preconditions: 已安装 rank_bm25 + jieba
    Steps:
      1. python3.11 -c "
        from ai_service.engine.bm25_retriever import BM25Retriever
        bm25 = BM25Retriever()
        corpus = ['2026年6月25日至7月15日报名','河海大学校训是艰苦朴素实事求是','计算机等级考试9月举行']
        ids = [1, 2, 3]
        bm25.build(corpus, ids)
        results = bm25.retrieve('计算机等级考试', top_k=3)
        assert len(results) > 0, f'Empty results: {results}'
        print(f'Results: {results}')
        "
    Expected Result: BM25 返回包含 "计算机等级考试" 相关的结果
    Failure Indicators: 空结果 / score 全 0
    Evidence: .sisyphus/evidence/task-7-bm25-basic.txt

  Scenario: BM25 + jieba 中文效果
    Tool: Bash
    Preconditions: jieba 已安装
    Steps:
      1. python3.11 -c "
        import jieba
        tokens = list(jieba.lcut('2026年研究生网上报名6月25日开始'))
        print(f'Tokens: {tokens}')
        assert len(tokens) >= 5, 'Tokenization too granular'
        "
    Expected Result: 正确识别 "研究生"、"网上报名" 等中文词
    Failure Indicators: 分词粒度过细或过粗
    Evidence: .sisyphus/evidence/task-7-jieba-tokenization.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-7-bm25-basic.txt`
  - [ ] `.sisyphus/evidence/task-7-jieba-tokenization.txt`

  **Commit**: YES (group with Task 8)
  - Message: `feat: BM25 retrieval with jieba tokenization`
  - Files: `ai_service/engine/bm25_retriever.py`, `ai_service/engine/pipeline.py`


- [x] 8. Task P1-2: RRF 融合

  **What to do**:
  - 创建 `ai_service/engine/fusion.py`：
    - 实现 RRF（Reciprocal Rank Fusion）：`score = 1 / (k + rank)`，k=60
    - 函数 `rrf_fuse(dense_results: list, bm25_results: list, k: float = 60.0, top_k: int = 10) -> list`
    - 去重：同一 doc_id 在两种检索中重复出现时取 max rank
    - 返回统一格式 `[(chunk_id, fused_score, dense_score, bm25_score)]`
  - 集成到 pipeline：query 流程中调用 dense + BM25 → RRF 融合 → 返回排序结果
  - TDD: 测试 RRF 融合的分数计算 + 排序正确性

  **Must NOT do**:
  - 不修改现有的 dense 或 BM25 单检索器
  - 如果 BM25 未启用（如文件不存在），自动降级为 dense-only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 纯算法实现，文件少
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 7)
  - **Parallel Group**: Wave 2 (with Task 7, 9)
  - **Blocks**: Task 10 (calibration)
  - **Blocked By**: Task 7

  **References**:
  - `ai_service/engine/bm25_retriever.py` — BM25 返回格式（RRF 消费）
  - `ai_service/engine/retriever.py` — dense 返回格式（RRF 消费）
  - `ai_service/engine/pipeline.py` — query 流程入口

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_rrf_fusion_basic`：两个检索器各返回结果 → 正确融合 + 排序
  - [ ] `test_rrf_dedup`：同一 doc_id 在双方结果中 → 融合后只出现一次
  - [ ] `test_rrf_dense_only_fallback`：BM25 结果为空 → 返回 dense-only 排序
  - [ ] `test_rrf_k_parameter`：不同 k 值 → 分数变化符合预期

  **QA Scenarios**:

  ```
  Scenario: RRF 融合排序
    Tool: Bash
    Preconditions: Task 7 完成，BM25 可用
    Steps:
      1. python3.11 -c "
        from ai_service.engine.fusion import rrf_fuse
        dense = [(1, 0.9), (2, 0.8), (3, 0.7)]  # (id, score)
        bm25 = [(2, 10.0), (3, 8.0), (4, 6.0)]
        fused = rrf_fuse(dense, bm25, k=60, top_k=3)
        print(f'Fused results: {fused}')
        assert len(fused) == 3
        assert fused[0][0] in (1, 2)  # top should be 1 or 2
        "
    Expected Result: 融合结果正确排序，assert 通过
    Failure Indicators: AssertionError / 空结果
    Evidence: .sisyphus/evidence/task-8-rrf-basic.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-8-rrf-basic.txt`

  **Commit**: YES (group with Task 7)
  - Message: `feat: RRF fusion for dense + BM25`
  - Files: `ai_service/engine/fusion.py`, `ai_service/engine/pipeline.py`


- [x] 9. Task P1-3: Cross-Encoder 重排

  **What to do**:
  - 创建 `ai_service/engine/reranker.py`：
    - 懒加载 BGE-reranker-base 模型（单例模式，同 embedding）
    - `rerank(query: str, candidates: list[(chunk_id, text)], max_length: int = 256) -> list[(chunk_id, rerank_score)]`
    - 从 RRF 结果中取 top 5 候选进行重排
    - 支持 max_length 参数（超长文本自动截断）
  - 集成到 pipeline：query 流程为 RRF 结果 → reranker 精排 → 最终结果
  - 可通过配置开关启用/禁用重排
  - TDD: 测试模型加载 + 重排结果排序

  **Must NOT do**:
  - 不修改 dense、BM25 或 RRF 代码
  - 如果模型加载失败（OOM），降级为 dense + BM25 无重排
  - 不实现多 batch 推理（单条 query 只需重排 5 个候选）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 重要但相对独立的模块
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES (代码独立)
  - **Parallel Group**: Wave 2 (with Task 7, 8)
  - **Blocks**: Task 10 (calibration), Task 11 (citation)
  - **Blocked By**: Task 1, 2 (hardware validation)

  **References**:
  - `ai_service/engine/embedding.py` — 模型懒加载模式参考（单例）
  - `ai_service/engine/vector_store.py` — FAISS 索引参考

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_reranker_load`：模型加载后 `is_loaded` 为 True
  - [ ] `test_reranker_rerank`：5 个候选经重排后分数分布合理
  - [ ] `test_reranker_ordering`：query 最相关的内容排在第一位
  - [ ] `test_reranker_fallback`：模型加载失败时返回原顺序

  **QA Scenarios**:

  ```
  Scenario: reranker 加载 + 基础重排
    Tool: Bash
    Preconditions: BGE-reranker-base 可加载（Task 2 已验证）
    Steps:
      1. python3.11 -c "
        from ai_service.engine.reranker import Reranker
        r = Reranker()
        assert r.is_loaded, 'Model not loaded'
        candidates = [(1, '计算机等级考试报名时间6月25日开始'), (2, '研究生选课通知'), (3, '校训艰苦朴素实事求是')]
        results = r.rerank('计算机等级考试什么时候报名', candidates)
        print(f'Reranked: {results}')
        assert results[0][0] == 1  # most relevant should rank first
        "
    Expected Result: "计算机等级考试" 相关的结果排第一，assert 通过
    Failure Indicators: OOM / 模型加载失败 / 排序错误
    Evidence: .sisyphus/evidence/task-9-reranker-basic.txt

  Scenario: 启用/禁用 reranker 不影响正常查询
    Tool: Bash (curl)
    Preconditions: ai_service 运行中
    Steps:
      1. curl -s -X POST http://localhost:8003/query -H 'Content-Type: application/json' -d '{"question":"河海大学校训","top_k":5,"use_reranker":false}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); assert len(d.get('sources',[])) >= 1; print(f'Sources: {len(d[\"sources\"])}')"
    Expected Result: 正常返回结果
    Failure Indicators: 报错
    Evidence: .sisyphus/evidence/task-9-reranker-disabled.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-9-reranker-basic.txt`
  - [ ] `.sisyphus/evidence/task-9-reranker-disabled.txt`

  **Commit**: YES (group with Task 10)
  - Message: `feat: Cross-Encoder reranker (BGE-reranker-base)`
  - Files: `ai_service/engine/reranker.py`, `ai_service/engine/pipeline.py`


- [x] 10. Task P1-4: 阈值校准

  **What to do**:
  - 使用 run_eval.py 对不同配置做消融实验：
    - Dense-only（当前基线）
    - Dense + BM25 + RRF（无重排）
    - Dense + BM25 + RRF + Reranker（最终配置）
  - 为每种配置：
    - 遍历阈值候选值（-1.0, 实际分数分布, 1.000001）
    - 计算每个阈值的 Precision / Recall / F1 / OOD 误答率
    - 选出 OOD 误答率 ≤10% + F1 最高的阈值
  - 输出校准报告到 `evals/calibration_report.json`
  - **最多 3 轮校准迭代**，每轮调整参数后重新执行
  - 将校准后的默认阈值写入配置

  **Must NOT do**:
  - 不超过 3 轮校准
  - 不在校准过程中修改业务代码（只改配置值）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要运行多轮实验、分析数据、确定参数
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO (sequential experiments)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 11
  - **Blocked By**: Task 6, 7, 8, 9

  **References**:
  - `evals/run_eval.py` — 评测框架（Task 6 产出）
  - `ai_service/engine/pipeline.py` — 最终查询管线
  - `ai_service/config.py` — 存储校准后的阈值

  **Acceptance Criteria**:

  **TDD**: N/A — 实验任务

  **QA Scenarios**:

  ```
  Scenario: 校准运行
    Tool: Bash
    Preconditions: evals/run_eval.py 可用，ai_service 运行中
    Steps:
      1. cd evals && python3.11 run_eval.py --mode retrieval --config dense-only --output results/calib_dense.json
      2. python3.11 run_eval.py --mode retrieval --config hybrid --output results/calib_hybrid.json
      3. python3.11 run_eval.py --mode retrieval --config hybrid+reranker --output results/calib_rerank.json
    Expected Result: 三个配置文件全部运行成功，输出 JSON
    Failure Indicators: 某些配置文件失败
    Evidence: .sisyphus/evidence/task-10-calibration-run.txt

  Scenario: 校准结果报告
    Tool: Bash
    Preconditions: 3 个校准运行完成
    Steps:
      1. python3.11 -c "
        import json
        for cfg in ['dense','hybrid','rerank']:
          d = json.load(open(f'evals/results/calib_{cfg}.json'))
          m = d['metrics']
          print(f'{cfg}: Hit@5={m[\"hit_at_5\"]:.3f} MRR={m[\"mrr_at_5\"]:.3f} OOD_reject={m[\"ood_rejection_rate\"]:.3f}')
        "
    Expected Result: 三种配置的指标对比清晰
    Failure Indicators: 文件缺失
    Evidence: .sisyphus/evidence/task-10-calibration-summary.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-10-calibration-run.txt`
  - [ ] `.sisyphus/evidence/task-10-calibration-summary.txt`
  - [ ] `evals/calibration_report.json`

  **Commit**: YES (group with Task 9)
  - Message: `feat: retrieval threshold calibration (3 rounds)`
  - Files: `evals/calibration_report.json`, `ai_service/config.py`


- [x] 11. Task P1-5: Citation 后校验

  **What to do**:
  - 创建 `ai_service/engine/citation.py`：
    - 从 LLM 回答中提取所有 `[Sx]` 引用（x 为数字）
    - 验证每个 `[Sx]` 对应的检索结果是否存在
    - 如果引用了不存在的 S 编号 → 从回答中删除该引用标记
    - 如果引用了错误的 S 编号 → 查找正确的 chunk 并修正
    - 返回修正后的回答 + citation 验证报告
  - 集成到 pipeline：LLM 生成 → citation 校验 → 最终回答
  - TDD: 测试各种 citation 格式的解析和修正

  **Must NOT do**:
  - 不重新调用 LLM（只做后处理）
  - 不做语义级别校验（只验证索引存在性）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要正则解析 + 逻辑校验 + 文本修改
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on pipeline integration)
  - **Parallel Group**: Wave 2 (with Task 10)
  - **Blocks**: Task 12-16 (P2)
  - **Blocked By**: Task 6, 7, 8, 10

  **References**:
  - `ai_service/engine/generator.py` — LLM 输出（citation 验证的输入）
  - `ai_service/engine/pipeline.py` — 集成位置
  - `ai_service/engine/prompts.py` — 定义 `[Sx]` 格式（Task 5 产出）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_extract_citations`：`[S1][S2]text[S3]` → 提取 [1, 2, 3]
  - [ ] `test_validate_citations_all_valid`：全部引用都存在 → 不改
  - [ ] `test_validate_citations_invalid`：引用 S5 但只有 3 个 sources → 删除 S5
  - [ ] `test_validate_citations_empty`：回答无引用 → 不改

  **QA Scenarios**:

  ```
  Scenario: Citation 校验 — 全部有效
    Tool: Bash
    Preconditions: python3.11
    Steps:
      1. python3.11 -c "
        from ai_service.engine.citation import validate_citations
        sources = [{'chunk_id': 1}, {'chunk_id': 2}, {'chunk_id': 3}]
        answer = '校训是艰苦朴素[S1][S2]。'
        result = validate_citations(answer, sources)
        print(f'Validated: {result[\"answer\"]}')
        assert '[S1]' in result['answer'] and '[S2]' in result['answer']
        assert result['invalid_count'] == 0
        print('PASS')
        "
    Expected Result: 引用不变，invalid_count=0
    Failure Indicators: AssertionError
    Evidence: .sisyphus/evidence/task-11-citation-valid.txt

  Scenario: Citation 校验 — 删除无效引用
    Tool: Bash
    Preconditions: python3.11
    Steps:
      1. python3.11 -c "
        from ai_service.engine.citation import validate_citations
        sources = [{'chunk_id': 1}]
        answer = '校训是艰苦朴素[S1]。还有信息[S5][S6]。'
        result = validate_citations(answer, sources)
        print(f'Validated: {result[\"answer\"]}')
        assert '[S5]' not in result['answer'] and '[S6]' not in result['answer']
        assert '[S1]' in result['answer']
        assert result['invalid_count'] == 2
        print('PASS')
        "
    Expected Result: [S5][S6] 被删除，[S1] 保留，invalid_count=2
    Failure Indicators: AssertionError
    Evidence: .sisyphus/evidence/task-11-citation-invalid.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-11-citation-valid.txt`
  - [ ] `.sisyphus/evidence/task-11-citation-invalid.txt`

  **Commit**: YES (group with Task 10)
  - Message: `feat: citation post-validation for LLM output`
  - Files: `ai_service/engine/citation.py`, `ai_service/engine/pipeline.py`


---

### Wave 3 — P2: 文档流水线

- [x] 12. Task P2-1: 文档状态机（模型 + 枚举 + 迁移）

  **What to do**:
  - 创建 `backend/app/models/enums.py`：
    - `DocumentStatus`: UPLOADED, PROCESSING, READY, FAILED
  - 修改现有 Document 模型（`backend/app/models/` 或用 SQLAlchemy 扩展）：
    - 添加 `status: DocumentStatus` 列（默认 UPLOADED）
    - 添加 `error_message: str | None` 列
    - 添加 `chunk_count: int` 列
    - 添加 `processed_at: datetime | None` 列
  - 创建 Alembic 迁移文件（如果已设 Alembic，增加迁移；否则先写到 init_db.sql）
  - 不修改现有业务逻辑（只加字段，不改变行为）
  - TDD: 测试新字段的默认值 + 状态转换

  **Must NOT do**:
  - 不破坏现有文档 CRUD 接口
  - status 字段加 nullable 默认值，不强制已有行迁移

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 跨后端 DB Schema 的改动
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 13, 14)
  - **Blocks**: Task 13, 14, 15, 16, 20
  - **Blocked By**: Task 1

  **References**:
  - `backend/app/database.py` — SQLAlchemy Base 声明
  - `backend/init_db.sql` — 当前 schema 定义
  - `backend/app/services/document_service.py` — 当前文档服务（需了解现有字段）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_document_status_default`：新文档创建后 status == UPLOADED
  - [ ] `test_document_status_transition`：状态正确流转 U→P→R 或 U→P→F
  - [ ] `test_document_error_message`：FAILED 状态包含 error_message
  - [ ] `test_existing_api_unaffected`：现有文档 CRUD API 仍正常工作

  **QA Scenarios**:

  ```
  Scenario: 创建文档检查默认状态
    Tool: Bash (curl)
    Preconditions: 后端运行中
    Steps:
      1. TOKEN=$(curl -s -X POST http://localhost:8002/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@test.com","password":"xxx"}' | python3.11 -c "import json,sys; print(json.load(sys.stdin).get('token',''))")
      2. curl -s -X POST http://localhost:8002/api/document -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"title":"测试","content":"测试内容","category":"其他"}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); print(f'Status: {d.get(\"status\",\"N/A\")}'); assert d.get('status') in ('UPLOADED','created','ok')"
    Expected Result: 文档创建成功，status 字段存在
    Failure Indicators: 接口返回 500 / status 字段缺失
    Evidence: .sisyphus/evidence/task-12-doc-status-default.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-12-doc-status-default.txt`

  **Commit**: YES (group with Task 13)
  - Message: `feat: document status state machine (UPLOADED→PROCESSING→READY→FAILED)`
  - Files: `backend/app/models/enums.py`, `backend/app/database.py`, `backend/init_db.sql`


- [x] 13. Task P2-2: 异步入库线程池

  **What to do**:
  - 在 `backend/app/services/document_service.py` 中实现 `IngestionService`：
    - 单工作线程 `ThreadPoolExecutor(max_workers=1)`
    - `enqueue(document_id: int)` — 将文档加入处理队列
    - 处理流程：读取文档内容 → 调 ai_service/process 或本地处理 → 更新状态
    - 处理完成后：status → READY，记录 chunk_count
    - 处理失败：status → FAILED，记录 error_message
    - 启动时恢复中断：扫描 PROCESSING 状态的文档 → 重置为 UPLOADED
  - 处理过程中调用 ai_service 的 `/process/content` 接口（之前已建的）进行向量化
  - TDD: 测试入队 → 处理完成 → 状态更新

  **Must NOT do**:
  - 不修改 ai_service 的现有逻辑
  - 不阻塞 API 请求（后台异步执行）

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: 需要理解 Flask/FastAPI 异步架构、线程安全、错误处理
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 14, 15, 16
  - **Blocked By**: Task 12

  **References**:
  - `backend/app/services/document_service.py` — 当前文档服务
  - `ai_service/main.py` — POST /process/content 端点（Task 0 之前已经添加）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_ingestion_enqueue`：入队后文档 status 变为 PROCESSING
  - [ ] `test_ingestion_complete`：处理完成后 status == READY, chunk_count > 0
  - [ ] `test_ingestion_failed`：处理异常时 status == FAILED, error_message 非空
  - [ ] `test_ingestion_restore`：启动时 PROCESSING 状态被重置为 UPLOADED

  **QA Scenarios**:

  ```
  Scenario: 文档上传 → 自动触发入库 → 完成
    Tool: Bash (curl)
    Preconditions: 后端运行中，ai_service 运行中
    Steps:
      1. 创建文档并获取 ID
      2. 等待 5 秒（异步入库）
      3. 查询文档状态
    Expected Result: 文档 status 从 UPLOADED → PROCESSING → READY
    Failure Indicators: 状态停留在 UPLOADED / 变为 FAILED
    Evidence: .sisyphus/evidence/task-13-ingestion-flow.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-13-ingestion-flow.txt`

  **Commit**: YES (group with Task 12)
  - Message: `feat: async document ingestion pipeline`
  - Files: `backend/app/services/document_service.py`


- [x] 14. Task P2-3: 单文档工件存储

  **What to do**:
  - 创建 `ai_service/engine/artifact_store.py`：
    - 每篇文档存为独立 JSON 文件：`data/artifacts/{doc_id}.json`
    - 格式：`{doc_id, title, category, source_url, chunks: [{content, chunk_index, vector_id}], metadata: {created_at, doc_length, chunk_count}}`
    - 方法：`save_doc(doc_id, chunks, metadata)`，`load_doc(doc_id)`，`delete_doc(doc_id)`，`list_docs()`
    - 方法：`rebuild_index()` — 扫描所有工件 → 重建 FAISS + BM25
    - 线程安全：写操作加文件锁
  - 初始化时，如果 `data/artifacts/` 目录不存在则创建
  - TDD: 测试保存 → 加载 → 删除 → 重建全流程

  **Must NOT do**:
  - 不替换现有的 faiss.index 单文件存储（两者共存，工件作为权威来源）
  - 不修改 FAISS 或 BM25 代码

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: I/O 密集型模块，需处理文件操作、线程安全
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 12, 15)
  - **Blocks**: Task 15, 16
  - **Blocked By**: Task 12, 13

  **References**:
  - `ai_service/engine/vector_store.py` — 当前 FAISS 存储（了解现有格式）
  - `ai_service/engine/pipeline.py` — 构建索引的地方（重建时需调用）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_artifact_save_load`：保存后加载内容一致
  - [ ] `test_artifact_delete`：删除后加载返回 None
  - [ ] `test_artifact_rebuild`：从工件重建索引后 vector count 匹配
  - [ ] `test_artifact_concurrent_safety`：并发写不损坏数据

  **QA Scenarios**:

  ```
  Scenario: 保存并加载文档工件
    Tool: Bash
    Preconditions: 已创建 data/artifacts/ 目录
    Steps:
      1. python3.11 -c "
        from ai_service.engine.artifact_store import ArtifactStore
        store = ArtifactStore('data/artifacts')
        store.save_doc('test_doc_1', [{'content':'测试','chunk_index':0,'vector_id':100}], {'created_at':'2026-07-15','chunk_count':1})
        doc = store.load_doc('test_doc_1')
        print(f'Loaded: {doc[\"doc_id\"]} with {doc[\"metadata\"][\"chunk_count\"]} chunks')
        assert doc['doc_id'] == 'test_doc_1'
        store.delete_doc('test_doc_1')
        assert store.load_doc('test_doc_1') is None
        print('Save/Load/Delete: PASS')
        "
    Expected Result: 保存→加载→删除 全流程通过
    Failure Indicators: AssertionError / 文件写入失败
    Evidence: .sisyphus/evidence/task-14-artifact-basic.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-14-artifact-basic.txt`

  **Commit**: YES (group with Task 15)
  - Message: `feat: per-document artifact storage (JSON)`
  - Files: `ai_service/engine/artifact_store.py`


- [x] 15. Task P2-4: 启动自恢复（从工件重建索引）

  **What to do**:
  - 在 `ai_service/engine/pipeline.py` 中增加启动检查：
    - 启动时检查 `data/artifacts/` 是否有 JSON 工件
    - 如果有工件但 `data/faiss.index` 不存在或损坏 → 自动用 `artifact_store.rebuild_index()` 重建
    - 重建过程：遍历所有工件 → 收集向量 + metadata → 构建 FAISS → 构建 BM25 → 保存
  - 日志输出重建进度（N 文档 → M chunks）
  - TDD: 测试索引损坏 → 自动重建成功

  **Must NOT do**:
  - 不需要用户手动触发
  - 不阻塞服务启动（重建时仍可接受请求）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 逻辑简单，改动范围小
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 16
  - **Blocked By**: Task 14

  **References**:
  - `ai_service/engine/pipeline.py` — 启动逻辑
  - `ai_service/engine/artifact_store.py` — rebuild_index 方法

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_rebuild_on_startup`：删除 faiss.index 后重启 → 自动重建
  - [ ] `test_rebuild_consistency`：重建后检索结果与原索引一致

  **QA Scenarios**:

  ```
  Scenario: 删除索引后自动重建
    Tool: Bash
    Preconditions: 有工件文件，删除 faiss.index
    Steps:
      1. Remove-Item ai_service/data/faiss.index -ErrorAction SilentlyContinue
      2. 启动 ai_service
      3. 检查日志包含 "rebuild" 或 "recovering"
      4. curl -s -X POST http://localhost:8003/query -H 'Content-Type: application/json' -d '{"question":"测试","top_k":1}' | python3.11 -c "import json,sys; d=json.load(sys.stdin); print(f'Sources: {len(d.get(\"sources\",[]))}')"
    Expected Result: 服务正常运行，自动重建索引
    Failure Indicators: 服务启动失败 / 查询报错
    Evidence: .sisyphus/evidence/task-15-rebuild-startup.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-15-rebuild-startup.txt`

  **Commit**: YES (group with Task 14)
  - Message: `feat: auto-rebuild index from artifacts on startup`
  - Files: `ai_service/engine/pipeline.py`


- [x] 16. Task P2-5: 上传→自动索引集成

  **What to do**:
  - 修改 `backend/app/routers/document.py` 的创建文档端点：
    - 创建文档后调用 `IngestionService.enqueue(document_id)`
  - 修改 `backend/app/routers/document.py` 的删除文档端点：
    - 删除文档后调用 `IngestionService.delete(document_id)`（触发 artifact 删除 + 索引重建）
  - 确保新创建的文档通过 `/process/content` 自动进入向量库
  - TDD: 测试创建文档后自动入队 → 处理完成 → 可检索到

  **Must NOT do**:
  - 不改变原有 API 响应格式（保持兼容）
  - 不阻塞请求（入队后立即返回 202）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 胶水代码，连接现有路由和新服务
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 17-21 (P3)
  - **Blocked By**: Task 13, 14, 15

  **References**:
  - `backend/app/routers/document.py` — 文档 CRUD 端点
  - `backend/app/services/document_service.py` — IngestionService（Task 13）
  - `ai_service/main.py` — POST /process/content

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_create_triggers_ingestion`：POST 创建文档 → status 变为 PROCESSING
  - [ ] `test_delete_triggers_removal`：DELETE 文档后 → 工件被删除
  - [ ] `test_doc_searchable_after_ingestion`：创建文档并等待处理 → /query 能检索到

  **QA Scenarios**:

  ```
  Scenario: 创建文档 → 自动索引 → 可检索
    Tool: Bash (curl)
    Preconditions: 后端 + ai_service 运行中
    Steps:
      1. 创建文档（POST /api/document）
      2. 等待 10 秒（异步处理）
      3. 查询刚创建的内容
    Expected Result: 新创建的文档内容可通过 RAG query 检索到
    Failure Indicators: 查询不到新内容 / 文档状态错误
    Evidence: .sisyphus/evidence/task-16-auto-index-flow.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-16-auto-index-flow.txt`

  **Commit**: YES (group with Task 13)
  - Message: `feat: auto-index new documents on upload`
  - Files: `backend/app/routers/document.py`


---

### Wave 4 — P3: 前端/基建

- [x] 17. Task P3-1: SourceCards 升级

  **What to do**:
  - 升级 `frontend/src/components/SourceCards.tsx`：
    - 在现有展开/折叠基础上添加：
      - 来源链接（URL clickable） `source_url`
      - 发布日期显示 `published_at`
      - 保持现有 score 进度条 + 颜色
    - 改为可折叠折叠面板（Ant Design Collapse），每篇来源一个 panel
    - Panel header 格式：`{title} — 相关度 {score}%`
    - Panel content: snippet（前 360 字符）+ 链接 + 日期
  - 类型定义移到 `frontend/src/types.ts`
  - TDD: 测试空 sources/完整 sources/截断 snippet

  **Must NOT do**:
  - 不改变整体页面布局
  - 不做动画/样式重构

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 前端组件开发，需要 UI 设计感
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 18, 19, 20, 21)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `frontend/src/pages/Chat.tsx` — 当前 sources 渲染方式（了解现状）
  - `frontend/src/services/api.ts` — API 返回的 sources 格式
  - `frontend/src/types.ts` — 类型定义（如果不存在则创建）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_source_cards_empty`：sources=[] → 不渲染任何内容
  - [ ] `test_source_cards_with_data`：有 sources → 显示 title + score + snippet
  - [ ] `test_source_cards_url`：有 source_url → 显示可点击链接
  - [ ] `test_source_cards_truncation`：过长 content → 截断为 360 字符 + "…"

  **QA Scenarios**:

  ```
  Scenario: SourceCards 显示来源信息
    Tool: Playwright
    Preconditions: 前端 + 后端运行
    Steps:
      1. 打开前端 Chat 页面
      2. 输入 "河海大学校训" 并发送
      3. 等待回答完成
    Expected Result: 回答下方显示来源卡片，包含标题、相关度、展开后可查看引用
    Failure Indicators: 无来源卡片 / 不包含链接
    Evidence: .sisyphus/evidence/task-17-source-cards.png
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-17-source-cards.png`
  - [ ] `.sisyphus/evidence/task-17-source-cards-html.txt`

  **Commit**: YES (group with Task 18)
  - Message: `feat: upgrade SourceCards with links and dates`
  - Files: `frontend/src/components/SourceCards.tsx`, `frontend/src/types.ts`


- [x] 18. Task P3-2: SSE 客户端完善

  **What to do**:
  - 创建 `frontend/src/lib/sse.ts`：
    - `SSEDecoder` 类：解析 SSE event stream（event/data/JSON parse）
    - `streamChat()` 函数：POST /api/ai/query/stream → 实时解析 SSE 事件
    - 事件类型：
      - `event: chunk` / `data: {"text":"..."}` — 逐字输出
      - `event: sources` / `data: {"sources":[...]}` — 最终来源列表
      - `event: error` / `data: {"message":"..."}` — 错误
    - AbortController 支持（取消请求）
    - 自动重连策略（5s 后重试，最多 3 次，仅对连接中断）
  - 集成到 Chat 页面替换现有 fetch 逻辑
  - TDD: 测试 SSEDecoder 解析各种事件格式

  **Must NOT do**:
  - 不修改后端 SSE 端点（保持兼容）
  - 不引入额外 SSE 库（纯原生实现）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 范围明确，单个模块
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 17, 19, 20, 21)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `frontend/src/pages/Chat.tsx` — 当前 SSE/流式消费方式
  - `backend/app/routers/ai.py` — SSE 端点格式

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_sse_decoder_chunk`：解析 `event: chunk\ndata: {"text":"好"}\n\n` → 得到 chunk 事件
  - [ ] `test_sse_decoder_sources`：解析 `event: sources\ndata: {"sources":[]}\n\n` → 得到 sources 事件
  - [ ] `test_sse_decoder_error`：解析 `event: error\ndata: {"message":"err"}\n\n` → 得到 error 事件
  - [ ] `test_sse_decoder_multi_chunk`：多个事件拼接 → 正确拆分为事件数组

  **QA Scenarios**:

  ```
  Scenario: SSE 流式问答
    Tool: Playwright
    Preconditions: 前端 + 后端 + ai_service 运行
    Steps:
      1. 打开 Chat 页面
      2. 输入问题，发送
      3. 观察是否逐字显示回答
    Expected Result: 回答以流式方式逐字出现，完成后显示来源
    Failure Indicators: 一次性显示不流式 / 无来源
    Evidence: .sisyphus/evidence/task-18-sse-stream.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-18-sse-stream.txt`

  **Commit**: YES (group with Task 17)
  - Message: `feat: SSE client with auto-reconnect`
  - Files: `frontend/src/lib/sse.ts`, `frontend/src/pages/Chat.tsx`


- [x] 19. Task P3-3: AuthContext 重构

  **What to do**:
  - 创建 `frontend/src/context/AuthContext.tsx`：
    - `AuthProvider` 组件包裹全局
    - `useAuth()` hook 返回 `{user, token, login, logout, isAuthenticated}`
    - 初始状态从 localStorage 恢复 token
    - login() 调用 POST /api/auth/login → 存储 token + user 到 localStorage
    - logout() 清除 token + user
    - 提供 `isAuthenticated` 保护路由
  - 修改现有 Login 页面使用 AuthContext
  - 修改现有页面使用 `useAuth()` 代替自管 token
  - TDD: 测试 login/logout/token 持久化

  **Must NOT do**:
  - 不改动后端认证逻辑
  - 不修改现有路由结构

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: 前端状态管理重构
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 17, 18, 20, 21)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `frontend/src/pages/Login.tsx` — 现有登录页面（自管 token）
  - `frontend/src/services/api.ts` — API 客户端（当前从哪里读 token）

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_auth_login`：login 后 token 和 user 存入 localStorage
  - [ ] `test_auth_logout`：logout 后 token 和 user 被清除
  - [ ] `test_auth_persistence`：刷新页面后从 localStorage 恢复 token
  - [ ] `test_auth_unauthenticated`：未登录时 isAuthenticated 为 false

  **QA Scenarios**:

  ```
  Scenario: 登录 → 刷新 → 保持登录状态
    Tool: Playwright
    Preconditions: 后端运行
    Steps:
      1. 打开前端页面
      2. 输入凭据登录
      3. 页面跳转到首页
      4. 刷新页面（F5）
    Expected Result: 刷新后仍处于登录状态，不跳回登录页
    Failure Indicators: 刷新后跳回登录页
    Evidence: .sisyphus/evidence/task-19-auth-persistence.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-19-auth-persistence.txt`

  **Commit**: YES (group with Task 18)
  - Message: `refactor: AuthContext with useAuth hook`
  - Files: `frontend/src/context/AuthContext.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/App.tsx`


- [x] 20. Task P3-4: Alembic 迁移

  **What to do**:
  - 初始化 Alembic：
    - 创建 `alembic.ini`（指向 `backend/alembic/`）
    - 创建 `backend/alembic/env.py`（使用现有 `database.py` 的 Base 元数据）
    - 创建 `backend/alembic/script.py.mako`
  - 生成初始迁移：扫描所有模型 → 自动生成 `20260716_0001_initial.py`
  - 为 Task 12 新增的字段生成第二迁移：`20260716_0002_document_status.py`
  - 验证：`alembic upgrade head` 创建所有表
  - 验证：`alembic downgrade -1` 回滚
  - TDD: 测试迁移可执行 + 可回滚

  **Must NOT do**:
  - 不修改任何现有模型（只生成迁移脚本）
  - 不删除现有 init_db.sql（保留作为参考）

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: 需要理解 SQLAlchemy + Alembic 集成
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 17, 18, 19, 21)
  - **Blocks**: Task 21
  - **Blocked By**: Task 12（需要了解模型的最终状态）

  **References**:
  - `backend/app/database.py` — SQLAlchemy Base
  - `backend/app/models/` — 所有 ORM 模型
  - Official Alembic docs (https://alembic.sqlalchemy.org/en/latest/)

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_alembic_upgrade_head`：`alembic upgrade head` 退出码 0
  - [ ] `test_alembic_downgrade`：`alembic downgrade -1` 退出码 0
  - [ ] `test_alembic_upgrade_again`：回滚后再次 upgrade 成功

  **QA Scenarios**:

  ```
  Scenario: Alembic 全迁移
    Tool: Bash
    Preconditions: 安装了 alembic
    Steps:
      1. cd backend && alembic upgrade head
    Expected Result: 成功创建所有表，退出码 0
    Failure Indicators: MigrationError / IntegrityError
    Evidence: .sisyphus/evidence/task-20-alembic-upgrade.txt

  Scenario: Alembic 回滚
    Tool: Bash
    Preconditions: upgrade head 成功
    Steps:
      1. cd backend && alembic downgrade -1
      2. alembic upgrade head
    Expected Result: 回滚 + 重新升级成功
    Failure Indicators: 回滚失败 / 再升级失败
    Evidence: .sisyphus/evidence/task-20-alembic-downgrade.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-20-alembic-upgrade.txt`
  - [ ] `.sisyphus/evidence/task-20-alembic-downgrade.txt`

  **Commit**: YES (group with Task 21)
  - Message: `feat: Alembic migrations for database schema management`
  - Files: `alembic.ini`, `backend/alembic/`


- [x] 21. Task P3-5: 配置集中化（.env + Pydantic）

  **What to do**:
  - 升级 `ai_service/config.py`（新建或重构）：
    - 从 15 项扩展到 ~25 项：增加 reranker, bm25, rejection, artifact 等配置
    - 全部从 `.env` 文件读取，默认值硬编码
  - 统一 `backend/app/config.py` 和 `ai_service/config.py` 的配置源
  - 配置项包括：
    - 检索：`REJECTION_THRESHOLD`, `BM25_K1`, `BM25_B`, `RRF_K`, `RERANKER_ENABLED`, `RERANKER_MODEL`, `RERANKER_MAX_LENGTH`, `RERANKER_TOP_K`
    - 文档：`ARTIFACT_DIR`, `INGESTION_TIMEOUT_S`
    - 基础设施：`EMBEDDING_MODEL`, `EMBEDDING_DIM`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`
  - 创建 `ai_service/.env.example` 示例文件
  - TDD: 测试配置从 .env 加载 + 默认值 fallback

  **Must NOT do**:
  - 不合并 backend 和 ai_service 的配置（各管各的，但使用相同设计模式）
  - 不修改现有环境变量名（新加项使用清晰的命名）

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 配置管理，代码量小
  - **Skills**: 无
  - **Skills Evaluated but Omitted**: 全部不适用

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Task 17, 18, 19, 20)
  - **Blocks**: None
  - **Blocked By**: Task 1, 20 (Alembic)

  **References**:
  - `backend/app/config.py` — 现有配置（参考格式）
  - `ai_service/engine/embedding.py` — 当前从环境变量读配置的地方
  - `.env` — 根目录的现有环境变量

  **Acceptance Criteria**:

  **TDD**:
  - [ ] `test_config_from_env`：设置环境变量 → 配置对象读到了正确值
  - [ ] `test_config_defaults`：不设置环境变量 → 使用默认值
  - [ ] `test_config_all_keys`：所有配置项都有默认值或 env 映射

  **QA Scenarios**:

  ```
  Scenario: 配置从 .env 加载
    Tool: Bash
    Preconditions: 设置测试环境变量
    Steps:
      1. $env:REJECTION_THRESHOLD='0.5'; python3.11 -c "
        from ai_service.config import settings
        assert settings.rejection_threshold == 0.5, f'Expected 0.5 got {settings.rejection_threshold}'
        print(f'REJECTION_THRESHOLD={settings.rejection_threshold}')
        "
    Expected Result: 配置正确读取环境变量值
    Failure Indicators: AssertionError / 默认值覆写
    Evidence: .sisyphus/evidence/task-21-config-env.txt

  Scenario: 配置使用默认值
    Tool: Bash
    Preconditions: 清除相关环境变量
    Steps:
      1. $env:REJECTION_THRESHOLD=''; python3.11 -c "
        from ai_service.config import settings
        assert settings.rejection_threshold is not None
        print(f'Default REJECTION_THRESHOLD={settings.rejection_threshold}')
        "
    Expected Result: 配置使用硬编码默认值
    Failure Indicators: KeyError / 报错
    Evidence: .sisyphus/evidence/task-21-config-default.txt
  ```

  **Evidence to Capture**:
  - [ ] `.sisyphus/evidence/task-21-config-env.txt`
  - [ ] `.sisyphus/evidence/task-21-config-default.txt`

  **Commit**: YES (group with Task 20)
  - Message: `refactor: centralized config with Pydantic Settings + .env`
  - Files: `ai_service/config.py`, `ai_service/.env.example`, `backend/app/config.py`


---

## Final Verification Wave

> 4 个评审 Agent 并行运行，全部通过后向用户展示结果，等待用户确认后才能标记完成。

- [ ] F1. **合规审计** — `oracle`

  读取 plan 全量内容，对照执行结果逐项核对：
  - For each "Must Have": 验证实现存在（读文件、curl 端点、运行命令）
  - For each "Must NOT Have": 搜索代码库是否有禁止模式
  - 检查 `.sisyphus/evidence/` 下证据文件是否存在
  - 对比交付物与 plan

  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **代码质量 + 测试** — `unspecified-high`

  运行 `pytest` + `vitest` 检查全部测试通过。
  审查所有变更文件的代码质量：
  - `as any` / `@ts-ignore` / `# type: ignore`
  - empty except / catch
  - `console.log` 在生产代码中
  - 未使用的 import
  - AI slop：过度注释、过度抽象、泛型命名（data/result/item）

  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **全场景 QA** — `unspecified-high` (+ `playwright` skill if UI)

  从干净状态开始，执行每一个 Task 的每一个 QA Scenario。
  测试跨任务集成（多个 Task 协同工作的端到端场景）。
  测试边界情况：空状态、无效输入、快速操作。
  截图/日志保存到 `.sisyphus/evidence/final-qa/`。

  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **范围一致性** — `deep`

  对每个 Task：读取 "What to do" → 读取实际 diff（git log/diff）。
  验证 1:1 — plan 中的所有内容都实现了（无遗漏），没有超出 plan 的内容（无 creep）。
  检查 "Must NOT do" 合规性。
  检测跨 Task 污染：Task N 修改了 Task M 的文件。

  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## 提交策略

- **Task 1-3**: `test: pytest + vitest infra`, `chore: hw validation`, `feat(evals): 50 eval test cases + baseline` — 3 commits
- **Task 4-6**: `feat: low-confidence rejection`, `feat: prompt engineering`, `feat(evals): evaluation framework` — 3 commits
- **Task 7-8**: `feat: BM25 retrieval`, `feat: RRF fusion` — 2 commits
- **Task 9-10**: `feat: Cross-Encoder reranker`, `feat: threshold calibration` — 2 commits
- **Task 11**: `feat: citation post-validation` — 1 commit
- **Task 12-13**: `feat: document state machine`, `feat: async ingestion` — 2 commits
- **Task 14-15**: `feat: artifact storage`, `feat: auto-rebuild on startup` — 2 commits
- **Task 16**: `feat: auto-index on upload` — 1 commit
- **Task 17-18**: `feat: SourceCards upgrade`, `feat: SSE client` — 2 commits
- **Task 19**: `refactor: AuthContext` — 1 commit
- **Task 20-21**: `feat: Alembic migrations`, `refactor: centralized config` — 2 commits

---

## 成功标准

### 验证命令
```bash
# P0 — 评测基线
cd evals && python3.11 run_eval.py --mode retrieval --config dense-only

# P1 — 混合检索评测
cd evals && python3.11 run_eval.py --mode retrieval --config hybrid+reranker

# P2 — 文档上线流程
# 上传文档 → 等待处理 → 检索新内容

# P3 — 前端
cd frontend && npx vitest run
cd frontend && npx vite build

# 全量测试
pytest backend/tests/
npx vitest run frontend/src/__tests__/
```

### 最终检查清单
- [ ] 全部 21 个 Task 完成
- [ ] All "Must Have" 已验证
- [ ] All "Must NOT Have" 已验证
- [ ] F1 合规审计 APPROVE
- [ ] F2 代码质量 APPROVE
- [ ] F3 全场景 QA 全部 PASS
- [ ] F4 范围一致性 APPROVE
- [ ] 用户明确确认"可以"

