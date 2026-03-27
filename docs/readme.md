[English](./docs/README.md) | [中文](./docs/README-zh.md)

# CPL-Clinic

> Intelligent Clinical Pathway Decision Support System — combining Large Language Models (LLMs), task decomposition, and a Clinical Pathway Language (CPL) to automate medical diagnosis and treatment workflows.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Project Structure](#project-structure)
- [Core Module Overview](#core-module-overview)
- [CPL Language Overview](#cpl-language-overview)
- [Installation & Configuration](#installation--configuration)
- [Usage](#usage)
  - [Web UI (Recommended)](#web-ui-recommended)
  - [CLI Mode](#cli-mode)
  - [Python API](#python-api)
- [End-to-End Execution Flow](#end-to-end-execution-flow)

---

## System Architecture

```
Raw Dialogue Input (text / Web UI / file)
    ↓
[Ambient — MultimodalAdapter]       ← Multimodal input normalisation
    ↓  RawClinicalData
[Commander — CommanderLLM]           ← LLM-driven label classification + task decomposition (with conditional branches)
    ↓  list[BaseTask | BranchNode]
[CPL — CPLGenerator]                 ← Rule-driven CPL script generation
    ↓  CPLScript (editable in Web UI)
[CPL — CPLInterpreter]               ← Parse CPL script into execution plan
    ↓  ExecutionPlan
[LLM Manager — LLMPool]             ← Multi-agent dispatch by TaskType
    ↓  ExecutionReport
[RAG — VectorMemory]                 ← Symptom–diagnosis pair archival (written after clinician confirmation)
```

---

## Project Structure

```
CPL-Clinic/
├── ambient/              # Multimodal input layer (file / API / audio)
│   ├── models.py         # Data models: RawClinicalData
│   ├── text_input.py     # Text input adapter
│   └── multimodal_adapter.py  # Unified entry point
├── commander/            # Task decomposition & orchestration layer
│   ├── task_schema.py    # TaskType enum, BaseTask and 11 subclasses
│   ├── commander_llm.py  # Core orchestrator: CommanderLLM (classify + decompose + CPL generation)
│   └── prompts.py        # LLM prompt templates
├── cpl/                  # Clinical Pathway Language layer
│   ├── models.py         # CPL data models: CPLNode, CPLScript
│   ├── generator.py      # Rule-driven CPL generator
│   ├── interpreter.py    # CPL interpreter → ExecutionPlan
│   ├── CPL_SPEC.md       # CPL language specification v1.1
│   └── cpl.tex           # CPL paper section (LaTeX)
├── llm_manager/          # LLM instance management layer
│   ├── models.py         # Configuration constants, system prompts
│   ├── manager.py        # High-level management interface: LLMManager
│   └── pool.py           # Agent pool & execution engine: LLMPool
├── rag/                  # RAG vector retrieval layer
│   └── rag_core.py       # FAISS vector database: VectorMemory
├── web/                  # Web frontend & backend
│   ├── backend.py        # FastAPI backend (SSE streaming execution)
│   └── static/index.html # Single-page frontend (block editor + CPL code editor)
├── config/               # Global configuration
│   └── settings.py       # Embedding model, paths and other constants
├── data/                 # Imported dialogue file directory
├── memory/               # FAISS index, pairs.jsonl, execution logs
├── utils/                # Data preprocessing utilities
├── test/                 # Test scripts
├── test_data/            # Test data
├── main.py               # CLI entry point
├── requirements.txt
└── README.md
```

---

## Core Module Overview

| Module | Core Class | Responsibility |
|---|---|---|
| **ambient** | `MultimodalAdapter` | Normalise file / string / API input into `RawClinicalData` |
| **commander** | `CommanderLLM` | LLM-driven dialogue label classification → task decomposition (supports conditional branches via `BranchNode`) |
| **cpl** | `CPLGenerator` / `CPLInterpreter` | Rule-driven CPL script generation; parse CPL into `ExecutionPlan` |
| **llm_manager** | `LLMManager` / `LLMPool` | Manage agent pool by `TaskType`, execute `ExecutionPlan` step by step |
| **rag** | `VectorMemory` | FAISS + `text2vec-base-chinese`, stores symptom–diagnosis pairs, supports similar case retrieval |
| **web** | FastAPI + index.html | Web UI with step-by-step execution, visual CPL editing, drag-and-drop reordering, RAG archival confirmation |

### Task Types (TaskType)

The system decomposes doctor–patient dialogues into the following 11 task types, each executed by a dedicated agent:

| TaskType | Description |
|---|---|
| `PATIENT_PROFILE` | Extract patient information (SOAP format) |
| `EXAMINATION_ORDER` | Issue examination / lab orders |
| `EXAM_EXECUTION` | Execute examinations |
| `PRESCRIPTION` | Issue prescriptions |
| `DIAGNOSTIC` | Diagnostic assessment & differential diagnosis |
| `SCHEDULE` | Create treatment plan & department routing |
| `TREATMENT_EXECUTION` | Execute specific treatment procedures |
| `NOTIFICATION` | Send notifications |
| `RESULT_REVIEW` | Interpret examination results |
| `ADMISSION_DISCHARGE` | Admission / discharge / transfer |
| `RECOVERY_ADVICE` | Recovery guidance |
| `ARCHIVE` | Archive case to RAG |

### LLM Configuration

| Role | Model | Purpose |
|---|---|---|
| Commander | `gpt-4.1` | Label classification, task decomposition |
| Agent Pool | `gpt-4.1-mini` | Concrete execution of each TaskType |

API calls are routed through AiHubMix. Set the environment variable `AIHUBMIX_API_KEY`.

---

## CPL Language Overview

CPL (Clinical Pathway Language) is the system's core DSL for describing clinical pathway execution flows. See `cpl/CPL_SPEC.md` for the full specification.

**7 Core Constructs:**

| Keyword | Purpose |
|---|---|
| `PATHWAY` | Declare pathway name (top-level container) |
| `ASSERT` | Pre-condition checks (informed consent, allergy info, etc.) |
| `STEP` | Define an execution step |
| `EXECUTE` | Invoke Agent / Protocol / RAG / Exam |
| `IF / ELIF / ELSE` | Conditional branching |
| `LOG` | Audit log entry |
| `NOTIFY` | Notify relevant parties |

**Example Script:**

```
PATHWAY "Outpatient Processing Pathway":
    ASSERT patient_consent == true
    ASSERT allergy_info != null

    STEP 1 "Extract Patient Profile":
        patient_profile = EXECUTE agent.patient_profile(dialogue)
        LOG "Patient profile extracted"

    STEP 2 "Issue Examinations":
        exam_order = EXECUTE agent.exam_order(patient_profile)

    STEP 3 "Diagnostic Assessment":
        diagnostic = EXECUTE agent.diagnostic(patient_profile, exam_order)
        IF diagnostic.confidence < 0.7:
            NOTIFY doctor "Diagnostic confidence insufficient, manual review recommended"

    STEP 4 "Archive Case":
        EXECUTE rag.archive(patient_profile, diagnostic)
```

---

## Installation & Configuration

```bash
# Install dependencies
pip install -r requirements.txt

# Set API Key
export AIHUBMIX_API_KEY="your-api-key"
```

---

## Usage

### Web UI (Recommended)

```bash
python -m uvicorn web.backend:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000`. The interface contains four panels:

1. **Dialogue Input** — Paste doctor–patient dialogue text
2. **Task Decomposition** — View the LLM-decomposed task list (including conditional branches)
3. **CPL Editor** — Block visualisation view (with drag-and-drop reordering) + code editor view; supports manual editing before execution
4. **Execution Results** — SSE streaming display of each step's execution status and results

After execution completes, the system prompts the clinician to review symptom–diagnosis pairs; upon confirmation, they are written to the RAG database.

### CLI Mode

```bash
python main.py --dialogue=data/1.txt
```

### Python API

```python
from ambient import MultimodalAdapter
from commander import CommanderLLM
from cpl import CPLGenerator, CPLInterpreter
from llm_manager import LLMManager

# 1. Load input
adapter = MultimodalAdapter()
raw_data = adapter.ingest_from_file("data/1.txt")

# 2. Initialise LLM
llms = LLMManager()

# 3. Task decomposition
commander = CommanderLLM(agent=llms.commander_agent)
tasks = await commander.decompose(raw_data)

# 4. Generate CPL
generator = CPLGenerator()
cpl_script = generator.generate(tasks, pathway_name="Outpatient Processing Pathway")

# 5. Interpret into execution plan
interpreter = CPLInterpreter()
plan = interpreter.interpret_script(cpl_script)

# 6. Execute
report = await llms._pool.execute_plan(plan, context={"dialogue": raw_data.content})
report.print_report()

# 7. Archive to RAG (in production, written after clinician confirmation)
llms._pool.rag.add_pair(
    record=report.variables.get("medical_record", ""),
    diagnostic=report.variables.get("diagnostic", "")
)
llms._pool.rag.save_index()
```

---

## End-to-End Execution Flow

```
                        ┌─────────────────────────────────────┐
                        │  Doctor–Patient Dialogue Input       │
                        │  (text / file / API)                 │
                        └──────────────┬──────────────────────┘
                                       ▼
                        ┌─────────────────────────────────────┐
                 Step 0 │  Ambient Input Normalisation         │
                        │  → RawClinicalData                   │
                        └──────────────┬──────────────────────┘
                                       ▼
                        ┌─────────────────────────────────────┐
                 Step 1 │  Commander Label Classification      │
                        │  + Task Decomposition                │
                        │  → list[BaseTask | BranchNode]       │
                        └──────────────┬──────────────────────┘
                                       ▼
                        ┌─────────────────────────────────────┐
                 Step 2 │  CPL Generator — Script Generation   │
                        │  → CPL Script (editable)             │
                        └──────────────┬──────────────────────┘
                                       ▼
                        ┌─────────────────────────────────────┐
                 Step 3 │  CPL Interpreter — Parse             │
                        │  → ExecutionPlan                     │
                        └──────────────┬──────────────────────┘
                                       ▼
                        ┌─────────────────────────────────────┐
                 Step 4 │  LLMPool — Step-by-Step Execution    │
                        │  → SSE streaming per-step results    │
                        └──────────────┬──────────────────────┘
                                       ▼
                        ┌─────────────────────────────────────┐
                 Step 5 │  Clinician Review → RAG Archival     │
                        │  → Symptom–diagnosis pairs → FAISS   │
                        └─────────────────────────────────────┘
```
