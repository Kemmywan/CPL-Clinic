# CPL (Clinical Pathway Language) 规范文档

> 版本：v1.1  日期：2026-03-23

---

## 一、概述

CPL（Clinical Pathway Language）是 AutoCPL 系统中用于描述临床路径执行流程的领域专用语言（DSL）。

**设计目标：**
- 将 Commander LLM 分解出的 Task 列表转化为**可审阅、可覆写、可执行**的脚本
- 医生能快速读懂并修改，系统能解析并自动执行
- 提供审计日志和安全断言保障
- 支持**条件分支**（含嵌套），覆盖诊断分流等非线性场景

**定位：**
```
医患对话 → Commander LLM → Task列表 → [CPL Generator] → CPL脚本 → CPL Interpreter → ExecutionPlan → Executor
                                         (线性/分支)            ↕                 (AgentCall序列)
                                                            医生审阅/覆写
```

---

## 二、脚本结构

一个完整的 CPL 脚本结构如下：

```
# 注释行（以 # 开头）
PATHWAY "<路径名称>":
    ASSERT <断言>                    # 前置条件
    STEP <编号> "<描述>":            # 步骤
        <CPL语句>
    # ... 更多STEP
    <收尾语句>                       # 归档/日志
```

### 2.1 PATHWAY 块
每个脚本有且仅有一个 `PATHWAY` 块作为顶层容器：
```
PATHWAY "低血钾处理路径 v1.0":
    ...
```

### 2.2 缩进规则
- 使用 4 空格缩进（不使用 Tab）
- `PATHWAY` 下一级缩进 4 空格
- `STEP` 内语句再缩进 4 空格
- `IF/ELIF/ELSE` 内语句缩进 4 空格

---

## 三、语言元素

### 3.1 基本类型

| 类型       | 示例                            | 说明         |
|------------|--------------------------------|-------------|
| 字符串     | `"血钾偏低"`                    | 双引号包裹   |
| 数值       | `3.5`, `18`                    | 整数或浮点数 |
| 布尔值     | `True`, `False`                | 大写开头     |
| 列表       | `["血常规", "血钾"]`            | JSON格式     |
| 字典       | `{"WBC": 5.2}`                 | JSON格式     |
| 枚举       | `"urgent"`, `"routine"`        | 字符串表示   |

### 3.2 Patient 对象

通过 `patient.` 前缀访问患者数据：

```
patient.age                     # 年龄
patient.gender                  # 性别
patient.serum_potassium         # 血钾浓度
patient.diagnosis               # 当前诊断
patient.allergies               # 过敏史列表
patient.vital_signs.bp          # 血压
patient.consent                 # 知情同意状态
```

---

## 四、核心语句

### 4.1 EXECUTE — 执行动作（核心）

调用 Agent 或协议执行具体操作，可带返回值赋值：

```
# 调用Agent（有返回值）
medical_record = EXECUTE agent.patient_profile(
    fields=["主诉", "现病史", "既往史", "过敏史"],
    output_format="SOAP"
)

# 调用Agent（无返回值）
EXECUTE agent.notification(recipients=["主治医生"], message="...")

# 发起检查
EXECUTE exam.draw_blood(target="serum_potassium")
```

**调用域（Call Domain）：**

CPL 中的 EXECUTE 语句支持三种调用域：

| 域前缀   | 含义                     | 示例                             |
|---------|--------------------------|----------------------------------|
| `agent` | Agent调用 → LLMPool调度    | `agent.patient_profile(...)`     |
| `rag`   | RAG归档操作               | `rag.archive(...)`               |
| `exam`  | 检查操作                   | `exam.draw_blood(...)`           |

**Agent 类型映射：**

| Agent标识                      | 对应TaskType             | 返回变量          |
|-------------------------------|--------------------------|-------------------|
| `agent.patient_profile`       | PATIENT_PROFILE          | `medical_record`  |
| `agent.examination_order`     | EXAMINATION_ORDER        | `exam_order`      |
| `agent.exam_execution`        | EXAM_EXECUTION           | `exam_data`       |
| `agent.prescription`          | PRESCRIPTION             | `prescription`    |
| `agent.diagnostic`            | DIAGNOSTIC               | `diagnostic`      |
| `agent.schedule`              | SCHEDULE                 | `schedule`        |
| `agent.treatment_execution`   | TREATMENT_EXECUTION      | `treatment`       |
| `agent.result_review`         | RESULT_REVIEW            | `exam_result`     |
| `agent.recovery_advice`       | RECOVERY_ADVICE          | `recovery`        |
| `agent.admission_discharge`   | ADMISSION_DISCHARGE      | `admission`       |
| `agent.notification`          | NOTIFICATION             | *(无返回值)*       |
| `agent.archive` / `rag.archive` | ARCHIVE               | *(无返回值)*       |

**STEP 默认标签：**

Generator 根据 TaskType 自动生成 STEP 描述标签：

| TaskType             | 默认标签     |
|----------------------|-------------|
| PATIENT_PROFILE      | 生成病历     |
| EXAMINATION_ORDER    | 检查申请     |
| EXAM_EXECUTION       | 检查执行     |
| PRESCRIPTION         | 开具处方     |
| DIAGNOSTIC           | AI诊断      |
| SCHEDULE             | 诊疗计划     |
| TREATMENT_EXECUTION  | 执行治疗     |
| RESULT_REVIEW        | 检查结果回读  |
| NOTIFICATION         | 发送通知     |
| ADMISSION_DISCHARGE  | 入出院管理   |
| RECOVERY_ADVICE      | 康复建议     |
| ARCHIVE              | 归档         |

### 4.2 ASSERT — 前置条件断言

在执行前验证必要条件，不满足则**阻断流程**：

```
ASSERT patient.consent == True, "患者未签署知情同意"
ASSERT patient.age >= 18, "本路径仅适用于成年患者"
ASSERT patient.allergies != UNSET, "过敏史信息缺失"
ASSERT exam.serum_potassium.done == True, "血钾检查未完成"
```

- 第一个参数：布尔表达式
- 第二个参数（逗号后）：断言失败时的提示消息

**自动生成规则：** Generator 根据 Task 列表自动推断所需的 ASSERT：

| 触发条件                                          | 自动生成的 ASSERT                                    |
|--------------------------------------------------|-----------------------------------------------------|
| 存在 TREATMENT_EXECUTION 类型的 Task              | `ASSERT patient.consent == True, "患者未签署知情同意"` |
| 存在 PRESCRIPTION 且 `contraindication_check=True` | `ASSERT patient.allergies != UNSET, "过敏史信息缺失，无法开具处方"` |

### 4.3 STEP — 步骤定义

```
STEP <编号> "<描述>":
    <一条或多条CPL语句>
```

- 编号为正整数，从 1 开始递增
- 描述用双引号包裹
- STEP 之间按编号顺序执行（尊重依赖关系）

### 4.4 IF / ELIF / ELSE — 条件分支

```
IF patient.serum_potassium < 3.5:
    EXECUTE agent.treatment_execution(treatment_type="补钾治疗")
ELIF patient.serum_potassium > 5.5:
    EXECUTE agent.treatment_execution(treatment_type="限制钾摄入")
ELSE:
    LOG "血钾正常，无需干预"
```

- 条件表达式支持 `<`, `>`, `<=`, `>=`, `==`, `!=`
- 支持嵌套分支

**BranchNode 条件分支（Generator）：**

当 Commander 产出包含 `BranchNode` 的 Task 列表时，Generator 自动生成条件分支 STEP：

```
STEP 3 "条件分支处理":
    IF diagnostic.primary_diagnosis == "颅内疾病":
        prescription = EXECUTE agent.prescription(
            medications=["甘露醇"],
            route="静脉注射"
        )
    ELIF diagnostic.primary_diagnosis == "普通头痛":
        prescription = EXECUTE agent.prescription(
            medications=["布洛芬"],
            route="口服"
        )
    ELSE:
        LOG "未匹配分支，进入默认处理" LEVEL WARNING
```

嵌套分支示例：
```
IF diagnostic.primary_diagnosis == "感染性疾病":
    IF exam_result.wbc > 15000:
        EXECUTE agent.treatment_execution(treatment_type="抗生素静脉注射")
    ELSE:
        EXECUTE agent.treatment_execution(treatment_type="口服抗生素")
ELSE:
    LOG "非感染性疾病" LEVEL INFO
```

**Interpreter 解析：** 条件分支被解析为 `ConditionalBlock`，executor 在运行时对条件求值并选择匹配的分支执行。

### 4.5 LOG — 审计日志

```
LOG "病历生成完成" LEVEL INFO
LOG "检测到低血钾" LEVEL WARNING
LOG "LLM调用失败" LEVEL ERROR
```

- `LEVEL` 可选值：`INFO`（默认）, `WARNING`, `ERROR`
- 所有 LOG 写入审计轨迹，支持后续回溯

### 4.6 NOTIFY — 发送通知

```
NOTIFY doctor.primary(message="血钾异常，已启动补钾方案")
NOTIFY nurse.duty(message="请每6小时抽血复查血钾")
NOTIFY patient.family(message="患者已入院")
```

**通知目标：**

| 标识               | 含义       |
|-------------------|-----------|
| `doctor.primary`  | 主治医生   |
| `nurse.duty`      | 值班护士   |
| `patient`         | 患者本人   |
| `patient.family`  | 患者家属   |

### 4.7 收尾区域（Epilogue）

ARCHIVE 类型的 Task 不生成独立的 STEP，而是放在所有 STEP 之后的收尾区域：

```
    # ---- 收尾 ----
    EXECUTE rag.archive(
        record=medical_record,
        exam=exam_result,
        diagnostic=diagnostic
    )
    LOG "已归档至RAG向量数据库" LEVEL INFO
    LOG "路径执行完成，已归档" LEVEL INFO
```

- 若存在 ARCHIVE Task 且 `rag_indexing=True`（默认），归档至 RAG 向量数据库
- 若 `rag_indexing=False`，归档至对应 EHR 系统
- 若无 ARCHIVE Task，仅生成 `LOG "路径执行完成" LEVEL INFO`

**人工确认归档流程：**

执行阶段遇到 `rag.archive` 调用时，系统**不会立即写入** RAG 数据库，而是：

1. 从当前变量空间提取 `(record, diagnostic)` 二元组
2. 暂存到 `session.pending_pairs`
3. 执行完成后，前端展示二元组审阅界面，医生可自由编辑 record 和 diagnostic 内容
4. 医生点击「确认归档」后，编辑后的二元组通过 `/api/confirm_pairs` 写入 RAG 向量数据库
5. 医生也可选择「跳过归档」，不存入 RAG

此设计确保进入 RAG 知识库的数据经过人工审核，避免 LLM 产出的噪声污染检索质量。

### 4.8 备注

原 `DEFINE protocol.<名称>` 语法已废弃，标准化操作统一通过 `EXECUTE agent.treatment_execution(...)` 实现。

---

## 五、完整示例

```python
# AutoCLP CPL Script
# Generated by: CPL Generator
# Date: 2026-03-17

PATHWAY "门诊低血钾处理路径":

    # 前置断言
    ASSERT patient.consent == True, "患者未签署知情同意"

    STEP 1 "生成病历":
        medical_record = EXECUTE agent.patient_profile(
            fields=["主诉", "现病史", "既往史", "过敏史"],
            output_format="SOAP"
        )
        LOG "病历生成完成" LEVEL INFO

    STEP 2 "诊疗计划":
        schedule = EXECUTE agent.schedule(
            input=medical_record
        )
        LOG "诊疗计划生成完成" LEVEL INFO

    STEP 3 "检查申请":
        exam_order = EXECUTE agent.examination_order(
            exam_items=["血常规", "血钾", "肾功能"],
            priority="urgent",
            target_department="检验科"
        )
        LOG "紧急检查已申请" LEVEL WARNING

    STEP 4 "检查结果回读":
        exam_result = EXECUTE agent.result_review(
            input=exam_order
        )
        IF exam_result.has_abnormal:
            NOTIFY doctor.primary(message="检查结果异常，请关注")
            LOG "检查结果异常" LEVEL WARNING

    STEP 5 "AI诊断":
        diagnostic = EXECUTE agent.diagnostic(
            input=exam_result,
            rag_context=AUTO
        )
        IF diagnostic.confidence < 0.6:
            LOG "诊断置信度偏低，建议人工复核" LEVEL WARNING
            NOTIFY doctor.primary(message="AI诊断置信度低于阈值，请复核")
        LOG "诊断完成" LEVEL INFO

    STEP 6 "康复建议":
        recovery = EXECUTE agent.recovery_advice(
            input=diagnostic
        )
        LOG "康复建议生成完成" LEVEL INFO

    # 收尾
    EXECUTE rag.archive(
        record=medical_record,
        exam=exam_result,
        diagnostic=diagnostic
    )
    LOG "已归档至RAG向量数据库" LEVEL INFO
    LOG "路径执行完成，已归档" LEVEL INFO
```

---

## 六、CPL Generator 使用方式

### 6.1 在 Python 中调用

```python
from cpl import CPLGenerator
from commander import CommanderLLM

# 方式1：规则驱动（确定性，推荐生产环境使用）
generator = CPLGenerator()
cpl_text = generator.render(tasks, pathway_name="门诊处理路径")
print(cpl_text)

# 方式2：获取结构化对象后再渲染
script = generator.generate(tasks)
print(script.pathway_name)
print(f"共 {len(script.nodes)} 个STEP")
print(script.render())

# 方式3：LLM驱动（灵活，适合探索）
commander = CommanderLLM(agent=llm_manager.commander_agent)
cpl_text = await commander.generate_cpl(tasks)
```

### 6.2 输入格式

`generate()` 和 `render()` 支持两种输入：

| 输入类型                           | 说明                                    |
|-----------------------------------|-----------------------------------------|
| `list[BaseTask]`                  | 线性Task列表，按拓扑排序后依次生成 STEP      |
| `list[BaseTask \| BranchNode]`    | 含条件分支的Task列表，BranchNode生成IF/ELIF/ELSE STEP |

**BranchNode 结构：**
```python
BranchNode(
    condition="diagnostic.primary_diagnosis",        # 条件变量
    branches=[                                       # (值, Task列表) 对
        ("颅内疾病", [PrescriptionTask(...)]),
        ("普通头痛", [PrescriptionTask(...)]),
    ],
    else_tasks=[NotificationTask(...)],              # ELSE分支（可选）
)
```

### 6.3 生成流程

1. **检测分支**：若输入包含 `BranchNode`，进入分支生成模式
2. **拓扑排序**（线性模式）：按 `depends_on` 对 Task 进行 Kahn 算法排序
3. **ASSERT 生成**：根据 Task 类型自动推断前置断言
4. **STEP 生成**：逐 Task 调用对应的 `_emit_xxx` 方法生成 CPL 代码行
5. **ARCHIVE 分离**：ARCHIVE Task 不进入 STEP，放入收尾区域
6. **路径名推断**：若未指定 `pathway_name`，根据 Task 组合自动推断

### 6.4 结构化输出：CPLScript

`generate()` 返回 `CPLScript` 对象：

```python
@dataclass
class CPLScript:
    pathway_name: str                    # 路径名称
    generated_at: str                    # 生成时间
    asserts: list[str]                   # ASSERT语句列表
    nodes: list[CPLNode]                 # STEP节点列表
    epilogue_lines: list[str]            # 收尾语句列表

@dataclass
class CPLNode:
    step_number: int                     # STEP编号
    label: str                           # STEP描述
    task_id: str                         # 关联的Task ID
    task_type: str                       # 关联的TaskType值
    body_lines: list[str]                # 该STEP内的CPL代码行
    depends_on: list[str]                # 依赖的task_id列表
```

### 6.5 两种生成方式对比

| 特性         | CPLGenerator（规则驱动） | CommanderLLM.generate_cpl（LLM驱动） |
|-------------|------------------------|--------------------------------------|
| 确定性       | ✅ 相同输入总是相同输出   | ❌ 每次可能不同                        |
| 速度         | ✅ 毫秒级               | ❌ 需要API调用                         |
| 可审计性     | ✅ 逻辑完全透明          | ⚠️ 依赖LLM行为                       |
| 灵活性       | ⚠️ 受限于预定义模板      | ✅ 可生成创造性表达                    |
| 成本         | ✅ 零API成本             | ❌ 消耗Token                          |
| 分支支持     | ✅ BranchNode→IF/ELIF/ELSE | ✅ 自由生成                          |
| 推荐场景     | 生产环境、批量处理        | 原型探索、复杂非标路径                  |

---

## 七、CPL Interpreter 使用方式

### 7.1 职责

Interpreter 将 CPL 脚本解析为结构化的 `ExecutionPlan`，供 Executor 调度执行：

- 解析 PATHWAY、ASSERT、STEP、IF/ELIF/ELSE 等语法结构
- 提取有序的 `AgentCall` 调用序列
- 保留 STEP 编号、依赖关系、参数等元信息
- 将条件分支解析为 `ConditionalBlock`，运行时由 Executor 求值

### 7.2 在 Python 中调用

```python
from cpl import CPLInterpreter

interpreter = CPLInterpreter()

# 方式1：从CPL文本解析
plan = interpreter.interpret(cpl_text)

# 方式2：从CPLScript对象解析（更可靠，无需正则匹配）
plan = interpreter.interpret_script(cpl_script)

# 获取所有Agent调用（含条件分支内的）
for call in plan.agent_calls_only():
    print(call.task_type, call.params)

# 查看执行计划摘要
print(plan.summary())
```

### 7.3 ExecutionPlan 结构

```python
@dataclass
class ExecutionPlan:
    pathway_name: str                          # 路径名称
    asserts: list[AssertEntry]                 # 前置断言
    calls: list[AgentCall | ConditionalBlock]  # 有序执行项列表
    logs: list[LogEntry]                       # LOG语句
    notifications: list[NotifyEntry]           # NOTIFY语句
```

### 7.4 AgentCall — 最小执行单元

```python
@dataclass
class AgentCall:
    call_id: str              # 唯一ID
    step_number: int          # 来源STEP编号
    step_label: str           # 来源STEP描述
    call_type: CallType       # AGENT / RAG / EXAM
    task_type: TaskType       # 映射到的TaskType（agent调用时有值）
    agent_name: str           # 原始agent名，如 "agent.patient_profile"
    variable_name: str        # 返回值变量名（无赋值时为空）
    params: dict              # 调用参数
    depends_on_steps: list    # 依赖的STEP编号
    source_line: str          # 原始CPL文本行（审计用）
    status: str               # pending / running / done / failed / skipped
    result: str               # 执行结果（executor填写）
```

### 7.5 ConditionalBlock — 条件分支执行块

```python
@dataclass
class ConditionalBlock:
    step_number: int
    step_label: str
    branches: list            # [(condition_expr, [AgentCall | ConditionalBlock | ...]), ...]
    else_items: list          # ELSE分支的执行项列表
```

Executor 遇到 `ConditionalBlock` 时，根据当前变量空间对各 `condition_expr` 求值，选择匹配的分支执行。

### 7.6 日志导出

Interpreter 解析完成后自动将 LOG 语句导出到 `memory/cpl_log/` 目录，文件名格式：`{时间戳}_{路径名}.json`。

---

## 八、关键设计原则

1. **可读性优先**：CPL 语法贴近自然语言与 Python，确保临床医生无编程背景也能理解
2. **安全守卫**：ASSERT 机制在执行前拦截不安全操作（未签同意、缺过敏史等）
3. **可审计性**：每一步都有 LOG，形成完整的审计轨迹；Interpreter 自动导出日志到 `memory/cpl_log/`
4. **人在回路**：CPL 脚本生成后须经医生审阅/覆写，再交 Interpreter 执行；RAG 归档前须经医生确认编辑症状-诊断二元组
5. **依赖可控**：STEP 按拓扑排序排列，依赖关系通过 `depends_on` 自动解析
6. **分支支持**：BranchNode → IF/ELIF/ELSE 条件分支，支持嵌套，覆盖诊断分流场景
7. **双入口解析**：Interpreter 支持从 CPL 文本（`interpret()`）和 CPLScript 对象（`interpret_script()`）两种方式解析
8. **可扩展**：新 TaskType 只需在 `CPLGenerator` 中添加对应 `_emit_xxx` 方法，并在 Interpreter 的 `_AGENT_NAME_TO_TASK_TYPE` 映射中注册
