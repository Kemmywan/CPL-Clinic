[English](https://github.com/Kemmywan/CPL-Clinic/blob/master/docs/readme.md) | [中文](https://github.com/Kemmywan/CPL-Clinic/blob/master/docs/readme-zh.md)

# CPL-Clinic

> 智能临床路径决策支持系统 —— 结合大语言模型（LLM）、任务分解与临床路径语言（CPL），自动化医疗诊疗流程。

---

## 目录

- [项目架构](#项目架构)
- [项目结构](#项目结构)
- [核心模块说明](#核心模块说明)
- [CPL 语言概览](#cpl-语言概览)
- [安装与环境配置](#安装与环境配置)
- [使用方式](#使用方式)
  - [Web UI（推荐）](#web-ui推荐)
  - [CLI 模式](#cli-模式)
  - [Python 代码调用](#python-代码调用)
- [端到端执行流程](#端到端执行流程)

---

## 项目架构

```
原始对话输入（文本 / Web UI / 文件）
    ↓
[Ambient — MultimodalAdapter]       ← 多模态输入标准化
    ↓  RawClinicalData
[Commander — CommanderLLM]           ← LLM 驱动的标签分类 + 任务分解（含条件分支）
    ↓  list[BaseTask | BranchNode]
[CPL — CPLGenerator]                 ← 规则驱动的 CPL 脚本生成
    ↓  CPLScript（可在 Web UI 中编辑）
[CPL — CPLInterpreter]               ← CPL 脚本解析为执行计划
    ↓  ExecutionPlan
[LLM Manager — LLMPool]             ← 多 Agent 按 TaskType 分派执行
    ↓  ExecutionReport
[RAG — VectorMemory]                 ← 症状-诊断二元组归档（医生确认后写入）
```

---

## 项目结构

```
CPL-Clinic/
├── ambient/              # 多模态输入层（文件/API/音频）
│   ├── models.py         # 数据模型：RawClinicalData
│   ├── text_input.py     # 文本输入适配器
│   └── multimodal_adapter.py  # 统一入口
├── commander/            # 任务分解与编排层
│   ├── task_schema.py    # 任务类型枚举 TaskType、BaseTask 及 11 种子类
│   ├── commander_llm.py  # 核心编排器：CommanderLLM（分类 + 分解 + CPL 生成）
│   └── prompts.py        # LLM 提示词模板
├── cpl/                  # 临床路径语言层
│   ├── models.py         # CPL 数据模型：CPLNode, CPLScript
│   ├── generator.py      # 规则驱动 CPL 生成器
│   ├── interpreter.py    # CPL 解释器 → ExecutionPlan
│   ├── CPL_SPEC.md       # CPL 语言规范 v1.1
│   └── cpl.tex           # CPL 论文章节（LaTeX）
├── llm_manager/          # LLM 实例管理层
│   ├── models.py         # 配置常量、系统提示词
│   ├── manager.py        # 高层管理接口：LLMManager
│   └── pool.py           # Agent 池与执行引擎：LLMPool
├── rag/                  # RAG 向量检索层
│   └── rag_core.py       # FAISS 向量数据库：VectorMemory
├── web/                  # Web 前端与后端
│   ├── backend.py        # FastAPI 后端（SSE 流式执行）
│   └── static/index.html # 单页前端（Block 编辑器 + CPL 代码编辑器）
├── config/               # 全局配置
│   └── settings.py       # 嵌入模型、路径等常量
├── data/                 # 导入的对话文件目录
├── memory/               # FAISS 索引、pairs.jsonl、执行日志
├── utils/                # 数据预处理辅助工具
├── test/                 # 测试脚本
├── test_data/            # 测试数据
├── main.py               # CLI 入口
├── requirements.txt
└── README.md
```

---

## 核心模块说明

| 模块 | 核心类 | 职责 |
|---|---|---|
| **ambient** | `MultimodalAdapter` | 将文件 / 字符串 / API 输入统一为 `RawClinicalData` |
| **commander** | `CommanderLLM` | LLM 驱动的对话标签分类 → 任务分解（支持条件分支 `BranchNode`） |
| **cpl** | `CPLGenerator` / `CPLInterpreter` | 规则驱动生成 CPL 脚本；解析 CPL 为 `ExecutionPlan` |
| **llm_manager** | `LLMManager` / `LLMPool` | 按 `TaskType` 管理 Agent 池，逐步执行 `ExecutionPlan` |
| **rag** | `VectorMemory` | FAISS + `text2vec-base-chinese`，存储症状-诊断二元组，支持相似病例检索 |
| **web** | FastAPI + index.html | Web UI，支持分步执行、CPL 可视化编辑、拖拽排序、RAG 归档确认 |

### 任务类型（TaskType）

系统将医患对话分解为以下 11 种任务类型，每种由专属 Agent 执行：

| TaskType | 说明 |
|---|---|
| `PATIENT_PROFILE` | 提取患者基本信息（SOAP 格式） |
| `EXAMINATION_ORDER` | 开具检查检验单 |
| `EXAM_EXECUTION` | 执行检查 |
| `PRESCRIPTION` | 开具处方 |
| `DIAGNOSTIC` | 诊断评估与鉴别诊断 |
| `SCHEDULE` | 制定治疗计划与科室流转 |
| `TREATMENT_EXECUTION` | 执行具体治疗操作 |
| `NOTIFICATION` | 发送通知 |
| `RESULT_REVIEW` | 检查结果判读 |
| `ADMISSION_DISCHARGE` | 入院/出院/转科 |
| `RECOVERY_ADVICE` | 康复指导 |
| `ARCHIVE` | 病例归档至 RAG |

### LLM 配置

| 角色 | 模型 | 用途 |
|---|---|---|
| Commander | `gpt-4.1` | 标签分类、任务分解 |
| Agent Pool | `gpt-4.1-mini` | 各 TaskType 的具体执行 |

通过 AiHubMix API 调用，需设置环境变量 `AIHUBMIX_API_KEY`。

---

## CPL 语言概览

CPL（Clinical Pathway Language）是系统的核心 DSL，用于描述临床路径执行流程。详见 `cpl/CPL_SPEC.md`。

**7 个核心构造：**

| 关键字 | 用途 |
|---|---|
| `PATHWAY` | 声明路径名称（顶层容器） |
| `ASSERT` | 前置条件检查（知情同意、过敏信息等） |
| `STEP` | 定义执行步骤 |
| `EXECUTE` | 调用 Agent / Protocol / RAG / Exam |
| `IF / ELIF / ELSE` | 条件分支 |
| `LOG` | 审计日志记录 |
| `NOTIFY` | 通知相关方 |

**示例脚本：**

```
PATHWAY "门诊处理路径":
    ASSERT patient_consent == true
    ASSERT allergy_info != null

    STEP 1 "提取患者档案":
        patient_profile = EXECUTE agent.patient_profile(dialogue)
        LOG "患者档案已提取"

    STEP 2 "开具检查":
        exam_order = EXECUTE agent.exam_order(patient_profile)

    STEP 3 "诊断评估":
        diagnostic = EXECUTE agent.diagnostic(patient_profile, exam_order)
        IF diagnostic.confidence < 0.7:
            NOTIFY doctor "诊断置信度不足，建议人工复核"

    STEP 4 "病例归档":
        EXECUTE rag.archive(patient_profile, diagnostic)
```

---

## 安装与环境配置

```bash
# 安装依赖
pip install -r requirements.txt

# 设置 API Key
export AIHUBMIX_API_KEY="your-api-key"
```

---

## 使用方式

### Web UI（推荐）

```bash
python -m uvicorn web.backend:app --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000`，界面包含四个面板：

1. **对话输入** — 粘贴医患对话文本
2. **任务分解** — 查看 LLM 分解出的任务列表（含条件分支）
3. **CPL 编辑器** — Block 可视化视图（支持拖拽排序）+ 代码编辑视图，可手动修改后执行
4. **执行结果** — SSE 流式展示每步执行状态与结果

执行完成后，系统会提示医生审核症状-诊断二元组，确认后写入 RAG 数据库。

### CLI 模式

```bash
python main.py --dialogue=data/1.txt
```

### Python 代码调用

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

# 4. 生成 CPL
generator = CPLGenerator()
cpl_script = generator.generate(tasks, pathway_name="门诊处理路径")

# 5. 解释为执行计划
interpreter = CPLInterpreter()
plan = interpreter.interpret_script(cpl_script)

# 6. 执行
report = await llms._pool.execute_plan(plan, context={"dialogue": raw_data.content})
report.print_report()

# 7. 归档到 RAG（生产环境中由医生确认后写入）
llms._pool.rag.add_pair(
    record=report.variables.get("medical_record", ""),
    diagnostic=report.variables.get("diagnostic", "")
)
llms._pool.rag.save_index()
```

---

## 端到端执行流程

```
                        ┌──────────────────────────────┐
                        │  医患对话输入（文本/文件/API） │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                 Step 0 │  Ambient 输入标准化            │
                        │  → RawClinicalData            │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                 Step 1 │  Commander 标签分类 + 任务分解  │
                        │  → list[BaseTask | BranchNode]│
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                 Step 2 │  CPL Generator 生成脚本        │
                        │  → CPL Script（可编辑）        │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                 Step 3 │  CPL Interpreter 解析          │
                        │  → ExecutionPlan              │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                 Step 4 │  LLMPool 逐步执行              │
                        │  → SSE 流式返回每步结果        │
                        └──────────────┬───────────────┘
                                       ▼
                        ┌──────────────────────────────┐
                 Step 5 │  医生审核 → RAG 归档            │
                        │  → 症状-诊断二元组写入 FAISS   │
                        └──────────────────────────────┘
```


