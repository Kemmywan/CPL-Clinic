# AutoCLP

> 智能临床路径决策支持系统 —— 结合大语言模型（LLM）、任务分解与临床路径语言（CPL），自动化医疗诊疗流程。

---

## 目录

- [项目架构](#项目架构)
- [项目结构](#项目结构)
- [安装与环境配置](#安装与环境配置)
- [Quick Start](#quick-start)
- [模块接口文档](#模块接口文档)
  - [1. Ambient 模块 — 多模态输入层](#1-ambient-模块--多模态输入层)
  - [2. Commander 模块 — 任务分解与编排层](#2-commander-模块--任务分解与编排层)
  - [3. CPL 模块 — 临床路径语言层](#3-cpl-模块--临床路径语言层)
  - [4. LLM Manager 模块 — 大模型管理层](#4-llm-manager-模块--大模型管理层)
  - [5. RAG 模块 — 向量检索增强层](#5-rag-模块--向量检索增强层)
  - [6. Config 模块 — 全局配置](#6-config-模块--全局配置)
  - [7. Utils 模块 — 辅助工具](#7-utils-模块--辅助工具)
- [端到端数据流](#端到端数据流)
- [接口速查表](#接口速查表)
- [使用示例](#使用示例)

---

## 项目架构

```
原始对话输入
    ↓
[Ambient — MultimodalAdapter]       ← 多模态输入标准化
    ↓  RawClinicalData
[Commander — CommanderLLM]           ← LLM 驱动的任务分解
    ↓  list[BaseTask]
[CPL — CPLGenerator]                 ← 规则驱动的 CPL 脚本生成
    ↓  CPLScript
[CPL — CPLInterpreter]               ← CPL 脚本解析为执行计划
    ↓  ExecutionPlan
[LLM Manager — LLMPool]             ← 多 Agent 并行执行
    ↓  ExecutionReport
[RAG — VectorMemory]                 ← 病例归档与相似检索
```

---

## 项目结构

```
AutoCLP/
├── ambient/              # 多模态输入层（文件/API/音频）
│   ├── models.py         # 数据模型：RawClinicalData, InputSource, InputModality
│   ├── text_input.py     # 文本输入适配器：TextInputAdapter
│   └── multimodal_adapter.py  # 统一入口：MultimodalAdapter
├── commander/            # 任务分解与编排层
│   ├── task_schema.py    # 任务数据模型：TaskType, BaseTask 及 11 种子类
│   ├── commander_llm.py  # 核心编排器：CommanderLLM, TaskFactory
│   └── prompts.py        # LLM 提示词模板
├── cpl/                  # 临床路径语言层
│   ├── models.py         # CPL 数据模型：CPLNode, CPLScript
│   ├── generator.py      # 规则驱动 CPL 生成器：CPLGenerator
│   ├── interpreter.py    # CPL 解释器：CPLInterpreter → ExecutionPlan
│   └── CPL_SPEC.md       # CPL 语言规范 v1.0
├── llm_manager/          # LLM 实例管理层
│   ├── models.py         # 配置常量、系统提示词、LLMEntry
│   ├── manager.py        # 高层管理接口：LLMManager
│   └── pool.py           # Agent 池与执行引擎：LLMPool, ExecutionReport
├── rag/                  # RAG 向量检索层
│   └── rag_core.py       # FAISS 向量数据库：VectorMemory
├── config/               # 全局配置
│   └── settings.py       # 嵌入模型、路径等常量
├── data/                 # 导入的对话文件目录
├── memory/               # FAISS 数据库与执行日志
├── raw/                  # 原始数据集
├── test/                 # 测试脚本
├── test_data/            # 测试数据
├── utils/                # 数据预处理辅助工具
├── main.py               # 主流程入口（CLI）
├── requirements.txt
└── README.md
```

---

## 安装与环境配置

```bash
pip install -r requirements.txt
```

需要设置环境变量 `AIHUBMIX_API_KEY`（或在代码中传入 `api_key` 参数）。

---

## Quick Start

```bash
# CLI 模式：从文件读入对话
python main.py --dialogue=data/1.txt
```

---

## 模块接口文档

### 1. Ambient 模块 — 多模态输入层

> 路径：`ambient/` &nbsp;|&nbsp; 职责：将不同来源的临床数据统一为 `RawClinicalData` 对象

#### 1.1 数据模型 (`ambient/models.py`)

**枚举 `InputSource`** — 输入来源

| 值 | 说明 |
|---|---|
| `FILE` | 从 txt/json 文件读取 |
| `API` | 从 Web 前端/REST API 接收 |
| `AUDIO` | 音频转写（预留） |
| `REALTIME` | 实时流式输入（预留） |

**枚举 `InputModality`** — 输入模态

| 值 | 说明 |
|---|---|
| `TEXT` | 纯文本对话 |
| `AUDIO` | 音频（预留） |
| `MULTIMODAL` | 混合模态（预留） |

**数据类 `RawClinicalData`** — 标准化临床数据对象

| 字段 | 类型 | 说明 |
|---|---|---|
| `content` | `str` | 原始临床对话文本（核心字段） |
| `source` | `InputSource` | 数据来源 |
| `modality` | `InputModality` | 输入模态 |
| `timestamp` | `str` | 采集时间（ISO 格式，自动生成） |
| `metadata` | `dict` | 扩展元数据（文件名、语言等） |

| 方法 | 返回 | 说明 |
|---|---|---|
| `is_valid()` | `bool` | 基础校验：content 非空 |
| `summary()` | `str` | 日志摘要（前 60 字符预览） |

#### 1.2 文本输入适配器 (`ambient/text_input.py`)

**类 `TextInputAdapter`**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `from_txt_file()` | `(path: str) -> RawClinicalData` | 单个对象 | 读取整个 txt 文件为一条对话 |
| `from_json_file()` | `(path: str, dialogue_key: str = "dialogue") -> Generator[RawClinicalData]` | 生成器 | 逐条读取 JSON 数组中的对话 |
| `from_string()` | `(text: str, source: InputSource = InputSource.API) -> RawClinicalData` | 单个对象 | 从字符串直接创建（API 输入） |

#### 1.3 多模态适配器 (`ambient/multimodal_adapter.py`)

**类 `MultimodalAdapter`** — 统一入口，当前支持 TEXT，预留 AUDIO / REALTIME 扩展

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `ingest_from_file()` | `(path: str) -> RawClinicalData` | 单个对象 | 自动识别 txt/json 并加载 |
| `ingest_batch_from_json()` | `(path: str, dialogue_key: str = "dialogue") -> Generator[RawClinicalData]` | 生成器 | 批量加载（测试/评估场景） |
| `ingest_from_string()` | `(text: str) -> RawClinicalData` | 单个对象 | 字符串直入（前端 API） |
| `ingest_from_audio()` | `(audio_path: str)` | `NotImplementedError` | **[预留]** 音频转写 |
| `ingest_realtime_stream()` | `(stream)` | `NotImplementedError` | **[预留]** 实时流式输入 |

---

### 2. Commander 模块 — 任务分解与编排层

> 路径：`commander/` &nbsp;|&nbsp; 职责：将医患对话分解为结构化任务列表，并可生成 CPL 脚本

#### 2.1 任务类型定义 (`commander/task_schema.py`)

**枚举 `TaskType`** — 11 种任务类型，覆盖完整诊疗流程

| 枚举值 | 说明 |
|---|---|
| `PATIENT_PROFILE` | 提取患者基本信息（SOAP 格式） |
| `EXAMINATION_ORDER` | 开具检查检验单 |
| `PRESCRIPTION` | 开具处方 |
| `DIAGNOSTIC` | 诊断评估与鉴别诊断 |
| `SCHEDULE` | 制定治疗计划与科室流转 |
| `TREATMENT_EXECUTION` | 执行具体治疗操作 |
| `NOTIFICATION` | 发送通知（医生/护士/家属） |
| `RESULT_REVIEW` | 检查结果判读 |
| `ADMISSION_DISCHARGE` | 入院/出院/转科 |
| `RECOVERY_ADVICE` | 出院后康复指导 |
| `ARCHIVE` | 病例归档至 EHR/RAG |

**枚举 `TaskStatus`** — 任务执行状态

| 值 | 说明 |
|---|---|
| `PENDING` | 等待执行 |
| `RUNNING` | 正在执行 |
| `DONE` | 执行完成 |
| `FAILED` | 执行失败 |
| `OVERRIDDEN` | 被医生覆盖 |

**数据类 `BaseTask`** — 任务基类

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | `str` | 唯一 UUID |
| `task_type` | `TaskType` | 任务类型枚举 |
| `status` | `TaskStatus` | 当前状态（默认 PENDING） |
| `created_at` | `str` | 创建时间 |
| `transaction_id` | `str` | 审计追踪标识 |
| `depends_on` | `list[str]` | 前置依赖任务 ID 列表 |
| `override_log` | `list[dict]` | 医生覆盖记录 |
| `cpl_ref` | `str` | 关联 CPL 脚本节点 ID |

| 方法 | 说明 |
|---|---|
| `mark_overridden(field_name, old_val, new_val, operator)` | 记录医生对字段的覆盖操作 |

**任务子类一览**

| 子类 | 关键字段 |
|---|---|
| `PatientProfileTask` | `fields`, `source_dialogue`, `output_format` |
| `ExaminationOrderTask` | `exam_items`, `priority`, `reason`, `target_department` |
| `PrescriptionTask` | `medications`, `route`, `pharmacy_instruction`, `contraindication_check` |
| `DiagnosticTask` | `differential_diagnoses`, `primary_diagnosis`, `evidence_refs`, `rag_context_used`, `confidence` |
| `ScheduleTask` | `planned_steps`, `estimated_duration`, `department_routing`, `priority` |
| `TreatmentExecutionTask` | `treatment_type`, `protocol_ref`, `executor_role`, `preconditions`, `monitoring_plan` |
| `NotificationTask` | `recipients`, `message`, `urgency`, `channel`, `trigger_condition` |
| `ResultReviewTask` | `exam_ref`, `result_data`, `interpretation`, `abnormal_flags`, `requires_action` |
| `AdmissionDischargeTask` | `action`, `ward`, `discharge_summary`, `follow_up_plan`, `instructions` |
| `RecoveryAdviceTask` | `lifestyle_recommendations`, `dietary_restrictions`, `medication_continuation`, `follow_up_schedule`, `red_flags` |
| `ArchiveTask` | `archive_targets`, `ehr_system`, `rag_indexing`, `audit_trail` |

#### 2.2 任务工厂 (`commander/commander_llm.py`)

**类 `TaskFactory`**

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `build()` | `(item: dict, depends_map: dict) -> BaseTask` | 任务子类实例 | 根据 `task_type` 字段实例化对应子类 |

#### 2.3 核心编排器 (`commander/commander_llm.py`)

**类 `CommanderLLM`**

```python
def __init__(self, agent: AssistantAgent)
```

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `decompose()` | `async (raw_data: RawClinicalData) -> list[BaseTask]` | 有序任务列表 | 分析对话并分解为任务 |
| `generate_cpl()` | `async (tasks: list[BaseTask]) -> str` | CPL 脚本字符串 | 将任务列表转为 CPL（LLM 驱动） |
| `process()` | `async (raw_data: RawClinicalData) -> (list[BaseTask], str)` | (任务列表, CPL脚本) | 一步到位：对话 → 任务 + CPL |

#### 2.4 提示词模板 (`commander/prompts.py`)

| 常量 | 用途 |
|---|---|
| `TASK_DECOMPOSE_PROMPT` | 输入医患对话，输出 JSON 任务数组 |
| `CPL_GENERATE_PROMPT` | 输入任务 JSON，输出 CPL 脚本 |

---

### 3. CPL 模块 — 临床路径语言层

> 路径：`cpl/` &nbsp;|&nbsp; 职责：CPL 脚本的数据模型、生成与解释执行

#### 3.1 CPL 数据模型 (`cpl/models.py`)

**数据类 `CPLNode`** — 单个 STEP 块

| 字段 | 类型 | 说明 |
|---|---|---|
| `step_number` | `int` | 步骤编号（从 1 开始） |
| `label` | `str` | 可读描述 |
| `task_id` | `str` | 关联任务 ID |
| `task_type` | `str` | 关联 TaskType |
| `body_lines` | `list[str]` | STEP 内的 CPL 代码行 |
| `depends_on` | `list[str]` | 依赖的任务 ID |

| 方法 | 返回 | 说明 |
|---|---|---|
| `render(indent="    ")` | `str` | 渲染为格式化 CPL STEP 块 |

**数据类 `CPLScript`** — 完整 CPL 脚本

| 字段 | 类型 | 说明 |
|---|---|---|
| `pathway_name` | `str` | 路径名称 |
| `generated_at` | `str` | 生成时间 |
| `header_comments` | `list[str]` | 头部注释 |
| `asserts` | `list[str]` | ASSERT 语句（前置条件） |
| `nodes` | `list[CPLNode]` | 有序 STEP 节点 |
| `epilogue_lines` | `list[str]` | 尾部归档语句 |

| 方法 | 返回 | 说明 |
|---|---|---|
| `render(indent="    ")` | `str` | 渲染完整 CPL 脚本文本 |

#### 3.2 CPL 生成器 (`cpl/generator.py`)

**类 `CPLGenerator`** — 规则驱动（非 LLM），确定性生成

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `generate()` | `(tasks: list[BaseTask], pathway_name: str = None) -> CPLScript` | CPLScript 对象 | 将任务列表转为结构化 CPL（含拓扑排序） |
| `render()` | `(tasks: list[BaseTask], pathway_name: str = None) -> str` | CPL 文本 | 一步到位：任务 → CPL 文本 |

> 对比：`CommanderLLM.generate_cpl()` 是 LLM 驱动（灵活但非确定性），`CPLGenerator` 是规则驱动（确定性，适合生产环境）。

#### 3.3 CPL 解释器 (`cpl/interpreter.py`)

**枚举 `CallType`** — 调用类型

| 值 | 说明 |
|---|---|
| `AGENT` | `agent.xxx()` → 提交至 LLMPool 执行 |
| `PROTOCOL` | `protocol.xxx` → 标准操作（无需 LLM） |
| `RAG` | `rag.archive()` → 归档操作 |
| `EXAM` | `exam.xxx()` → 检查请求 |

**数据类 `AgentCall`** — 最小执行单元

| 字段 | 类型 | 说明 |
|---|---|---|
| `call_id` | `str` | 唯一调用 UUID |
| `step_number` | `int` | 来源 STEP 编号 |
| `step_label` | `str` | 来源 STEP 描述 |
| `call_type` | `CallType` | 调用类型 |
| `task_type` | `TaskType \| None` | 映射到的 TaskType |
| `agent_name` | `str` | 原始 agent 名称 |
| `variable_name` | `str` | 返回值变量名 |
| `params` | `dict` | 调用参数 |
| `depends_on_steps` | `list[int]` | 依赖的 STEP 编号 |
| `source_line` | `str` | 原始 CPL 文本（审计） |
| `is_awaited` | `bool` | 是否有 AWAIT 前缀 |
| `status` | `str` | pending/running/done/failed/skipped |
| `result` | `str` | 执行结果 |
| `error` | `str` | 错误信息 |

**数据类 `ExecutionPlan`** — 完整执行计划

| 字段 | 类型 | 说明 |
|---|---|---|
| `pathway_name` | `str` | 路径名称 |
| `asserts` | `list[AssertEntry]` | 前置条件 |
| `calls` | `list[AgentCall]` | 有序 Agent 调用列表（核心） |
| `logs` | `list[LogEntry]` | LOG 语句 |
| `notifications` | `list[NotifyEntry]` | NOTIFY 语句 |

| 方法 | 返回 | 说明 |
|---|---|---|
| `agent_calls_only()` | `list[AgentCall]` | 仅筛选 AGENT 类型调用 |
| `summary()` | `str` | 执行计划文本摘要 |
| `export_logs()` | — | 将日志写入 `memory/cpl_log/` |

**类 `CPLInterpreter`** — 两种输入路径

| 方法 | 输入 | 返回 | 适用场景 |
|---|---|---|---|
| `interpret_script()` | `CPLScript` 对象 | `ExecutionPlan` | 从 CPLGenerator 直接传入（更规范） |
| `interpret()` | CPL 脚本文本 | `ExecutionPlan` | 从 CommanderLLM 或文件读入 |

#### 3.4 CPL 语言规范

详见 `cpl/CPL_SPEC.md`，核心语法元素：

| 关键字 | 用途 |
|---|---|
| `PATHWAY` | 声明路径名称 |
| `STEP` | 定义执行步骤 |
| `EXECUTE` | 调用 Agent / Protocol / RAG / Exam |
| `ASSERT` | 前置条件检查（知情同意、过敏信息等） |
| `IF / ELIF / ELSE` | 条件分支 |
| `REPEAT EVERY ... UNTIL` | 周期性监测循环 |
| `AWAIT` | 阻塞等待结果 |
| `LOG` | 审计日志记录 |
| `NOTIFY` | 通知相关方 |

---

### 4. LLM Manager 模块 — 大模型管理层

> 路径：`llm_manager/` &nbsp;|&nbsp; 职责：按 TaskType 管理和调度 LLM 实例

#### 4.1 配置常量与系统提示词 (`llm_manager/models.py`)

```python
DEFAULT_MODEL_STRONG   = "gpt-4.1"         # Commander 使用（强模型）
DEFAULT_MODEL_STANDARD = "gpt-4.1-mini"    # Agent Pool 默认（标准模型）
```

| 常量 | 类型 | 说明 |
|---|---|---|
| `SYSTEM_MESSAGES` | `dict[TaskType, str]` | 每种任务类型对应的中文系统提示词 |
| `COMMANDER_SYSTEM_MESSAGE` | `str` | Commander LLM 专用系统提示词 |

**数据类 `LLMEntry`** — Agent 池中的单个 LLM 条目

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_type` | `TaskType` | 关联任务类型 |
| `client` | `OpenAIChatCompletionClient` | OpenAI 兼容客户端 |
| `agent` | `AssistantAgent` | AgentChat 封装 |
| `model_name` | `str` | 模型标识 |
| `description` | `str` | 描述 |

#### 4.2 高层管理接口 (`llm_manager/manager.py`)

**类 `LLMManager`**

```python
def __init__(
    self,
    api_key: str = None,              # 默认从环境变量 AIHUBMIX_API_KEY 读取
    base_url: str = "https://aihubmix.com/v1",
    commander_model: str = DEFAULT_MODEL_STRONG,
    default_agent_model: str = DEFAULT_MODEL_STANDARD,
    auto_register_all: bool = True     # 初始化时自动注册全部 TaskType
)
```

| 方法/属性 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `commander_agent` | `@property` | `AssistantAgent` | 获取 Commander 专用 Agent |
| `get_agent()` | `(task_type: TaskType) -> AssistantAgent` | Agent | 获取指定 TaskType 的 Agent |
| `register_agent()` | `(task_type: TaskType, model: str = None, system_message: str = None)` | — | 手动注册/覆盖 Agent |
| `list_registered()` | `() -> list` | 已注册类型列表 | 查看已注册的 TaskType |

向后兼容属性：`agent_1`（PATIENT_PROFILE）、`agent_2`（SCHEDULE）、`agent_3`（DIAGNOSTIC）、`agent_4`（RECOVERY_ADVICE）、`agent_test`（EXAMINATION_ORDER）。

#### 4.3 Agent 池与执行引擎 (`llm_manager/pool.py`)

**类 `LLMPool`**

```python
def __init__(self, api_key: str, base_url: str)
```

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `register()` | `(task_type, model, system_message, description) -> LLMEntry` | LLMEntry | 注册/覆盖任务 LLM |
| `register_all_defaults()` | `(model: str = DEFAULT_MODEL_STANDARD)` | — | 批量注册全部 TaskType |
| `unregister()` | `(task_type: TaskType)` | — | 移除任务 LLM |
| `get_agent()` | `(task_type: TaskType) -> AssistantAgent` | Agent | 获取 Agent（需已注册） |
| `get_entry()` | `(task_type: TaskType) -> LLMEntry` | LLMEntry | 获取完整条目 |
| `has()` | `(task_type: TaskType) -> bool` | bool | 检查是否已注册 |
| `list_registered()` | `() -> list[dict]` | 列表 | 列出所有注册条目 |
| `execute_plan()` | `async (plan: ExecutionPlan, context: dict = None) -> ExecutionReport` | ExecutionReport | **核心**：执行 CPL 解释器产出的执行计划 |
| `rag` | `@property` | `VectorMemory` | 懒加载获取 RAG 实例 |
| `export_audit_log()` | `() -> str` | JSON 字符串 | 导出审计日志 |
| `get_audit_by_transaction()` | `(txn_id: str) -> dict` | 审计条目 | 按事务 ID 查询审计记录 |

**数据类 `ExecutionReport`** — 执行报告

| 字段 | 类型 | 说明 |
|---|---|---|
| `pathway_name` | `str` | 路径名称 |
| `call_results` | `list[CallResult]` | 各调用的执行结果 |
| `audit_entries` | `list[AuditEntry]` | 完整审计轨迹 |
| `variables` | `dict` | 最终变量空间（medical_record, diagnostic 等） |
| `total_calls` | `int` | 总调用数 |
| `succeeded` / `failed` / `skipped` | `int` | 成功/失败/跳过数 |

| 方法 | 说明 |
|---|---|
| `finalize()` | 计算汇总统计 |
| `print_report()` | 控制台打印执行报告 |

**数据类 `AuditEntry`** — 审计记录

| 字段 | 类型 | 说明 |
|---|---|---|
| `transaction_id` | `str` | 事务 ID |
| `step_number` | `int` | STEP 编号 |
| `step_label` | `str` | STEP 描述 |
| `action` | `str` | 操作描述 |
| `call_type` / `task_type` | `str` | 调用/任务类型 |
| `params` | `dict` | 参数 |
| `status` | `str` | running/done/failed/skipped/passed |
| `result_preview` | `str` | 结果预览（前 200 字符） |
| `started_at` / `finished_at` | `str` | 时间戳 |

---

### 5. RAG 模块 — 向量检索增强层

> 路径：`rag/` &nbsp;|&nbsp; 职责：基于 FAISS 的病例向量存储与相似检索

**类 `VectorMemory`**

```python
def __init__(
    self,
    dim: int = 768,
    index_file: str = "memory/vector.faiss",
    pair_file: str = "memory/pairs.jsonl",
    emb_model_name: str = "shibing624/text2vec-base-chinese"
)
```

| 方法 | 签名 | 返回 | 说明 |
|---|---|---|---|
| `add_pair()` | `(record: str, diagnostic: str)` | — | 添加一条（病历, 诊断）对并更新索引 |
| `batch_import()` | `(pairs: List[Dict])` | — | 批量导入 |
| `search()` | `(query: str, top_k: int = 5) -> List[Dict]` | 相似病例列表 | 向量相似度检索 |
| `save_index()` | `()` | — | 持久化 FAISS 索引到磁盘 |
| `get_pair()` | `(idx: int) -> Dict` | `{record, diagnostic}` | 按索引获取 |
| `__len__()` | `() -> int` | int | 库中病例对数量 |

检索结果格式：

```python
{"record": "患者病历文本", "diagnostic": "诊断结论", "score": 0.123}  # score 为 L2 距离，越小越相似
```

---

### 6. Config 模块 — 全局配置

> 路径：`config/settings.py`

| 常量 | 值 | 说明 |
|---|---|---|
| `EMB_MODEL_NAME` | `"shibing624/text2vec-base-chinese"` | 嵌入模型 |
| `EMB_DIM` | `768` | 嵌入维度 |
| `MEMORY_INDEX_FILE` | `"memory/vector.faiss"` | FAISS 索引路径 |
| `MEMORY_TRIPLE_FILE` | `"memory/pairs.jsonl"` | 病例对存储路径 |

---

### 7. Utils 模块 — 辅助工具

> 路径：`utils/`

#### `extract_dialogue.py` — 对话提取工具（CLI）

```bash
python utils/extract_dialogue.py -lmi=500 -lma=600 -t=100 -s=T
# 输出: test_data/2020_500_600_100.txt
```

| 参数 | 说明 |
|---|---|
| `-lmi / --lengthMin` | 最小对话长度（字符数） |
| `-lma / --lengthMax` | 最大对话长度 |
| `-t / --total` | 提取记录数 |
| `-s / --save` | 是否保存（T/F） |

处理流程：`read_raw()` → `split_records()` → `parse_record()` → `filter_by_length()` → `save_json()`

#### `extract_script.py` — 批量提取脚本

以 100 字符步长（0–5000）循环调用 `extract_dialogue.py`，每档提取 20 条。

---

## 端到端数据流

```
1. 输入标准化    MultimodalAdapter.ingest_from_file()  →  RawClinicalData
2. 任务分解      CommanderLLM.decompose(RawClinicalData) →  list[BaseTask]
3. CPL 生成      CPLGenerator.generate(list[BaseTask])   →  CPLScript
4. 脚本解释      CPLInterpreter.interpret_script(CPLScript) →  ExecutionPlan
5. 计划执行      LLMPool.execute_plan(ExecutionPlan)      →  ExecutionReport
6. 病例归档      VectorMemory.add_pair(record, diagnostic)
```

---

## 接口速查表

| 模块 | 核心类 | 关键方法 | 返回类型 |
|---|---|---|---|
| **ambient** | `MultimodalAdapter` | `ingest_from_file()`, `ingest_batch_from_json()`, `ingest_from_string()` | `RawClinicalData` |
| **commander** | `CommanderLLM` | `decompose()`, `generate_cpl()`, `process()` | `list[BaseTask]`, `str` |
| | `TaskFactory` | `build()` | `BaseTask` 子类 |
| **cpl** | `CPLGenerator` | `generate()`, `render()` | `CPLScript`, `str` |
| | `CPLInterpreter` | `interpret()`, `interpret_script()` | `ExecutionPlan` |
| **llm_manager** | `LLMManager` | `get_agent()`, `register_agent()`, `commander_agent` | `AssistantAgent` |
| | `LLMPool` | `execute_plan()`, `register()`, `get_agent()` | `ExecutionReport` |
| **rag** | `VectorMemory` | `add_pair()`, `search()`, `save_index()` | `List[Dict]` |

---

## 使用示例

### 完整流水线（端到端）

```python
from ambient import MultimodalAdapter
from commander import CommanderLLM
from cpl import CPLGenerator, CPLInterpreter
from llm_manager import LLMManager

# 1. 加载输入
adapter = MultimodalAdapter()
raw_data = adapter.ingest_from_file("data/1.txt")

# 2. 初始化 LLM
llms = LLMManager()

# 3. 任务分解
commander = CommanderLLM(agent=llms.commander_agent)
tasks = await commander.decompose(raw_data)

# 4. 生成 CPL（确定性规则驱动）
generator = CPLGenerator()
cpl_script = generator.generate(tasks, pathway_name="门诊处理路径")

# 5. 解释 CPL 为执行计划
interpreter = CPLInterpreter()
plan = interpreter.interpret_script(cpl_script)

# 6. 执行
report = await llms._pool.execute_plan(plan, context={"dialogue": raw_data.content})
report.print_report()

# 7. 归档到 RAG
llms._pool.rag.add_pair(
    record=report.variables.get("medical_record", ""),
    diagnostic=report.variables.get("diagnostic", "")
)
llms._pool.rag.save_index()
```

### 仅任务分解

```python
commander = CommanderLLM(agent=llms.commander_agent)
tasks = await commander.decompose(raw_data)
for task in tasks:
    print(f"{task.task_type.value}: {task.task_id}")
```

### 批量处理

```python
adapter = MultimodalAdapter()
for raw in adapter.ingest_batch_from_json("test_data/2020_0_100_20.txt"):
    tasks = await commander.decompose(raw)
    # ... 后续处理
```


