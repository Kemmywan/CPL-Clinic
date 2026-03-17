# CPL (Clinical Pathway Language) 规范文档

> 版本：v1.0 | 作者：AutoCLP Team | 日期：2026-03-17

---

## 一、概述

CPL（Clinical Pathway Language）是 AutoCLP 系统中用于描述临床路径执行流程的领域专用语言（DSL）。

**设计目标：**
- 将 Commander LLM 分解出的 Task 列表转化为**可审阅、可覆写、可执行**的脚本
- 医生能快速读懂并修改，系统能解析并自动执行
- 提供审计日志和安全断言保障

**定位：**
```
医患对话 → Commander LLM → Task列表 → [CPL Generator] → CPL脚本 → CPL Interpreter → 执行
                                                                   ↕
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
| 时间区间   | `duration(6, "hours")`         | 专用函数     |
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

# 调用标准协议
EXECUTE protocol.initiate_potassium_supplement

# 发起检查
EXECUTE exam.draw_blood(target="serum_potassium")
```

**Agent 类型映射：**

| Agent标识                      | 对应TaskType             | 返回变量          |
|-------------------------------|--------------------------|-------------------|
| `agent.patient_profile`       | PATIENT_PROFILE          | `medical_record`  |
| `agent.examination_order`     | EXAMINATION_ORDER        | `exam_order`      |
| `agent.prescription`          | PRESCRIPTION             | `prescription`    |
| `agent.diagnostic`            | DIAGNOSTIC               | `diagnostic`      |
| `agent.schedule`              | SCHEDULE                 | `schedule`        |
| `agent.treatment_execution`   | TREATMENT_EXECUTION      | `treatment`       |
| `agent.result_review`         | RESULT_REVIEW            | `exam_result`     |
| `agent.recovery_advice`       | RECOVERY_ADVICE          | `recovery`        |
| `agent.admission_discharge`   | ADMISSION_DISCHARGE      | `admission`       |

### 4.2 ASSERT — 前置条件断言

在执行前验证必要条件，不满足则**阻断流程**：

```
ASSERT patient.consent == True, "患者未签署知情同意"
ASSERT patient.age >= 18, "本路径仅适用于成年患者"
ASSERT patient.allergies != UNSET, "过敏史信息缺失"
ASSERT exam.serum_potassium.done == True BEFORE protocol.initiate_potassium_supplement
```

- 第一个参数：布尔表达式
- 第二个参数（逗号后）：断言失败时的提示消息
- `BEFORE` 关键字：指定断言针对的后续操作

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
    EXECUTE protocol.initiate_potassium_supplement
ELIF patient.serum_potassium > 5.5:
    EXECUTE protocol.restrict_potassium_intake
ELSE:
    LOG "血钾正常，无需干预"
```

- 条件表达式支持 `<`, `>`, `<=`, `>=`, `==`, `!=`
- 支持嵌套

### 4.5 REPEAT ... UNTIL — 循环监测

适用于周期性监测场景：

```
REPEAT EVERY duration(6, "hours") UNTIL patient.serum_potassium >= 3.5:
    EXECUTE exam.draw_blood(target="serum_potassium")
    EXECUTE protocol.adjust_supplement
```

- `duration(n, unit)` 支持的单位：`"minutes"`, `"hours"`, `"days"`, `"weeks"`
- `UNTIL` 后接退出条件

### 4.6 AWAIT — 等待异步结果

```
AWAIT exam_result
result = LOAD exam_result.serum_potassium
```

- 阻塞当前流程，等待指定对象可用
- 常用于等待检查结果回填

### 4.7 LOG — 审计日志

```
LOG "病历生成完成" LEVEL INFO
LOG "检测到低血钾" LEVEL WARNING
LOG "LLM调用失败" LEVEL ERROR
```

- `LEVEL` 可选值：`INFO`（默认）, `WARNING`, `ERROR`
- 所有 LOG 写入审计轨迹，支持后续回溯

### 4.8 NOTIFY — 发送通知

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

### 4.9 DEFINE — 可复用协议定义

```
DEFINE protocol.initiate_potassium_supplement:
    DOSAGE: 10 mmol/h IV
    DURATION: duration(24, "hours")
    MONITOR: patient.serum_potassium EVERY duration(6, "hours")
    CONTRAINDICATION: patient.renal_failure == True
```

- 定义后可在 EXECUTE 中通过 `protocol.<名称>` 引用
- 类似函数定义，封装标准化医疗操作

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
        AWAIT exam_result
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

### 6.2 两种生成方式对比

| 特性         | CPLGenerator（规则驱动） | CommanderLLM.generate_cpl（LLM驱动） |
|-------------|------------------------|--------------------------------------|
| 确定性       | ✅ 相同输入总是相同输出   | ❌ 每次可能不同                        |
| 速度         | ✅ 毫秒级               | ❌ 需要API调用                         |
| 可审计性     | ✅ 逻辑完全透明          | ⚠️ 依赖LLM行为                       |
| 灵活性       | ⚠️ 受限于预定义模板      | ✅ 可生成创造性表达                    |
| 成本         | ✅ 零API成本             | ❌ 消耗Token                          |
| 推荐场景     | 生产环境、批量处理        | 原型探索、复杂非标路径                  |

---

## 七、关键设计原则

1. **可读性优先**：CPL 语法贴近自然语言与 Python，确保临床医生无编程背景也能理解
2. **安全守卫**：ASSERT 机制在执行前拦截不安全操作（未签同意、缺过敏史等）
3. **可审计性**：每一步都有 LOG，形成完整的审计轨迹
4. **人在回路**：CPL 脚本生成后须经医生审阅/覆写，再交 Interpreter 执行
5. **依赖可控**：STEP 按拓扑排序排列，依赖关系通过 `depends_on` 自动解析
6. **可扩展**：新 TaskType 只需在 `CPLGenerator` 中添加对应 `_emit_xxx` 方法
