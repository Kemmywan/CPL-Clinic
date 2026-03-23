# commander/prompts.py

# ==================== Commander 通用系统提示词 ====================

COMMANDER_SYSTEM_MESSAGE = """你是一个专业的医疗临床路径规划助手（Commander LLM）。
你具备以下核心能力：
1. 病情标签分类：根据医患对话判断病情类型
2. 任务分解：将临床意图分解为结构化的Task列表（支持条件分支）
3. CPL脚本生成：将Task列表转化为可执行的CPL（Clinical Pathway Language）脚本

请严格按照用户指令中的输出格式要求进行输出，不要包含任何额外解释文字。"""

# ==================== 标签分类 ====================

LABEL_CLASSIFY_PROMPT = """
你是一个专业的医疗症状分类器。根据输入的医患对话，判断该对话主要涉及以下哪种病症：

1. 感冒
2. 腹痛
3. 头痛
4. 骨折
5. 失眠

如果对话内容不属于以上任何一种，请回答"无"。
只需回答标签名称（如"感冒"或"无"），不要包含任何额外解释文字。

## 医患对话：
{dialogue}
"""

VALID_LABELS = ["感冒", "腹痛", "头痛", "骨折", "失眠"]

# ==================== 五种标签的参考范式（来自label_handle.md） ====================

_PARADIGM_TEMPLATES = {
    "感冒": """
PatientProfileTask(fields=["symptoms", "onset_time", "medical_history"])
DiagnosticTask(
    differential_diagnoses=["viral_infection", "bacterial_infection", "allergic_rhinitis"],
    rag_context_used=True
)
ExaminationOrderTask(
    exam_items=["body_temperature", "throat_exam", "CRP", "WBC"],
    priority="normal"
)
ExamExecutionTask(exam_items=["body_temperature", "throat_exam", "CRP", "WBC"], data_mode="auto_generate")
IF DiagnosticTask.primary_diagnosis == "viral_infection":
    PrescriptionTask(medications=["rest", "fluids", "symptomatic_drug"], route="oral")
ELIF DiagnosticTask.primary_diagnosis == "bacterial_infection":
    PrescriptionTask(medications=["antibiotic"], contraindication_check=True)
ELIF DiagnosticTask.primary_diagnosis == "allergic_rhinitis":
    PrescriptionTask(medications=["antihistamine"], pharmacy_instruction="指导抗过敏药物使用")
ResultReviewTask(exam_ref="All", requires_action=True)
RecoveryAdviceTask(lifestyle_recommendations=["多休息", "多饮水"], red_flags=["高烧不退", "呼吸困难"])
ArchiveTask(record="medical_record", diagnostic="diagnostic")
""",
    "腹痛": """
PatientProfileTask(fields=["pain_location", "pain_type", "onset_time", "associated_symptoms"])
DiagnosticTask(
    differential_diagnoses=["消化道相关", "泌尿系统", "妇科", "急腹症"],
    rag_context_used=True
)
ExaminationOrderTask(
    exam_items=["腹部体检", "尿常规", "腹部彩超", "子宫附件检查"],
    priority="urgent"
)
ExamExecutionTask(exam_items=["腹部体检", "尿常规", "腹部彩超", "子宫附件检查"], data_mode="auto_generate")
IF DiagnosticTask.primary_diagnosis == "消化道相关":
    PrescriptionTask(medications=["抑酸药", "解痉药"], route="oral")
    ResultReviewTask(result_data="abdominal_ultrasound")
ELIF DiagnosticTask.primary_diagnosis == "妇科":
    ExaminationOrderTask(exam_items=["妇科B超", "HCG"], priority="urgent")
    ExamExecutionTask(exam_items=["妇科B超", "HCG"], data_mode="auto_generate")
    NotificationTask(recipients=["妇产科"], message="需会诊", urgency="high")
ELIF DiagnosticTask.primary_diagnosis == "急腹症":
    ScheduleTask(planned_steps=["紧急手术准备"], priority="highest")
    NotificationTask(recipients=["外科"], message="急腹症手术", urgency="emergency")
    AdmissionDischargeTask(action="admit", ward="急诊外科")
ELSE:
    RecoveryAdviceTask(follow_up_schedule="短期复诊")
ArchiveTask(record="medical_record", diagnostic="diagnostic")
""",
    "头痛": """
PatientProfileTask(fields=["pain_intensity", "pain_duration", "accompanying_symptoms"])
DiagnosticTask(
    differential_diagnoses=["紧张型头痛", "偏头痛", "颅内疾病", "感染"],
    rag_context_used=True
)
IF DiagnosticTask.primary_diagnosis in ["紧张型头痛", "偏头痛"]:
    PrescriptionTask(medications=["止痛药", "偏头痛特异药"], route="oral")
ELIF DiagnosticTask.primary_diagnosis == "颅内疾病":
    ExaminationOrderTask(exam_items=["脑CT", "MRI"], priority="urgent")
    ExamExecutionTask(exam_items=["脑CT", "MRI"], data_mode="auto_generate")
    IF ExamExecutionTask.result.abnormal == True:
        NotificationTask(recipients=["神经内科"], message="影像异常，疑似颅内病变", urgency="high")
        AdmissionDischargeTask(action="admit", ward="神经内科")
    ELSE:
        ResultReviewTask(result_data="脑CT|MRI", interpretation="影像学未见明显异常")
        RecoveryAdviceTask(lifestyle_recommendations=["观察随访", "定期复查"], red_flags=["头痛加重", "意识障碍"])
ELIF DiagnosticTask.primary_diagnosis == "感染":
    ExaminationOrderTask(exam_items=["血常规", "脑脊液检查"], priority="urgent")
    ExamExecutionTask(exam_items=["血常规", "脑脊液检查"], data_mode="auto_generate")
    IF ExamExecutionTask.result.WBC > 10000:
        PrescriptionTask(medications=["广谱抗生素"], route="iv")
        NotificationTask(recipients=["感染科"], message="白细胞升高，疑似细菌感染", urgency="high")
    ELSE:
        PrescriptionTask(medications=["抗病毒药物"], route="oral")
ResultReviewTask(requires_action=True)
RecoveryAdviceTask(lifestyle_recommendations=["规律作息", "避免触发因素"], red_flags=["意识障碍", "反复呕吐"])
ArchiveTask(record="medical_record", diagnostic="diagnostic")
""",
    "骨折": """
PatientProfileTask(fields=["受伤方式", "受伤时间", "功能障碍表现"])
ExaminationOrderTask(exam_items=["X光", "CT", "MRI"], priority="urgent")
ExamExecutionTask(exam_items=["X光", "CT", "MRI"], data_mode="auto_generate")
DiagnosticTask(
    differential_diagnoses=["骨折类型", "合并损伤"],
    rag_context_used=True
)
IF DiagnosticTask.primary_diagnosis == "骨折类型确定":
    TreatmentExecutionTask(treatment_type="复位与固定")
    NotificationTask(recipients=["急诊或骨科"], message="必要时手术会诊", urgency="high")
    AdmissionDischargeTask(action="admit", ward="骨科")
ResultReviewTask(result_data="X光|CT|MRI", interpretation="影像学诊断")
RecoveryAdviceTask(lifestyle_recommendations=["限制负重", "按时复查"], follow_up_schedule="骨科门诊")
ArchiveTask(record="medical_record", diagnostic="diagnostic")
""",
    "失眠": """
PatientProfileTask(fields=["失眠持续时间", "加重缓解因素", "日常影响"])
DiagnosticTask(
    differential_diagnoses=["暂时性失眠", "焦虑抑郁", "器质性疾病"],
    rag_context_used=True
)
IF DiagnosticTask.primary_diagnosis == "暂时性失眠":
    RecoveryAdviceTask(lifestyle_recommendations=["睡前避免蓝光", "规律作息"], red_flags=["症状加重"])
ELIF DiagnosticTask.primary_diagnosis == "焦虑抑郁":
    PrescriptionTask(medications=["助眠药", "抗焦虑药"], route="oral")
    NotificationTask(recipients=["心理科"], message="建议心理评估", channel="internal")
ELIF DiagnosticTask.primary_diagnosis == "器质性疾病":
    ExaminationOrderTask(exam_items=["甲状腺功能", "基础代谢检测"], priority="normal")
    ExamExecutionTask(exam_items=["甲状腺功能", "基础代谢检测"], data_mode="auto_generate")
ResultReviewTask(requires_action=True)
RecoveryAdviceTask(follow_up_schedule="2周后随访")
ArchiveTask(record="medical_record", diagnostic="diagnostic")
""",
}

# ==================== 任务分解（带分支）— 已知标签 ====================

TASK_DECOMPOSE_BRANCHED_PROMPT = """
你是一个专业的医疗临床路径规划助手（Commander LLM）。
你的任务是：根据输入的医患对话和指定的病情标签，**严格按照参考范式结构**生成一个带至少一个diagnosis条件分支和至少一个exam_result条件分支的Task列表。

## 可用Task类型：
- patient_profile, examination_order, exam_execution, prescription, diagnostic, schedule
- treatment_execution, notification, result_review, admission_discharge
- recovery_advice, archive

## 输出格式：
合法JSON数组，数组中每个元素可以是以下两种之一：

### 1. 普通Task
{{
  "task_type": "...",
  "summary": "该任务的简要描述",
  "depends_on": [],
  "priority": "routine",
  "params": {{...}}
}}

### 2. 条件分支节点
{{
  "type": "branch",
  "condition": "条件变量（如 diagnostic.primary_diagnosis）",
  "branches": [
    {{
      "condition_value": "分支条件值",
      "tasks": [普通Task, ...]
    }}
  ],
  "else_tasks": [普通Task, ...]
}}

## 分支使用说明：
条件分支不仅可以基于诊断结果（diagnostic.primary_diagnosis），还可以基于检查执行的结果（exam_execution.result）进行嵌套分支。
例如：先根据诊断分支，在某个诊断分支内执行检查后，再根据检查结果分支决定后续操作。

## 示例输出片段：
[
  {{"task_type": "patient_profile", "summary": "提取症状信息", "depends_on": [], "priority": "routine", "params": {{"fields": ["symptoms"]}}}},
  {{"task_type": "diagnostic", "summary": "鉴别诊断", "depends_on": ["patient_profile"], "priority": "routine", "params": {{"differential_diagnoses": ["A", "B"], "rag_context_used": true}}}},
  {{
    "type": "branch",
    "condition": "diagnostic.primary_diagnosis",
    "branches": [
      {{"condition_value": "A", "tasks": [
        {{"task_type": "examination_order", "summary": "申请检查", "depends_on": [], "priority": "urgent", "params": {{"exam_items": ["脑CT", "MRI"]}}}},
        {{"task_type": "exam_execution", "summary": "执行检查", "depends_on": ["examination_order"], "priority": "routine", "params": {{"exam_items": ["脑CT", "MRI"], "data_mode": "auto_generate"}}}},
        {{
          "type": "branch",
          "condition": "exam_execution.result.abnormal",
          "branches": [
            {{"condition_value": true, "tasks": [{{"task_type": "notification", "summary": "通知专科", "depends_on": [], "priority": "urgent", "params": {{"recipients": ["专科"], "message": "检查异常"}}}}]}}
          ],
          "else_tasks": [{{"task_type": "recovery_advice", "summary": "观察随访", "depends_on": [], "priority": "routine", "params": {{"lifestyle_recommendations": ["定期复查"]}}}}]
        }}
      ]}},
      {{"condition_value": "B", "tasks": [{{"task_type": "prescription", "summary": "开药B", "depends_on": [], "priority": "routine", "params": {{"medications": ["drugB"]}}}}]}}
    ],
    "else_tasks": []
  }},
  {{"task_type": "result_review", "summary": "回读结果", "depends_on": [], "priority": "routine", "params": {{"requires_action": true}}}}
]

## 当前病情标签: {label}

## 参考范式（请严格按照以下结构生成，参数值可根据对话实际内容调整）：
{paradigm}

## 当前医患对话：
{dialogue}

请严格按照参考范式的结构输出JSON数组，不要包含任何额外解释文字。
"""

# ==================== 任务分解（带分支）— 无匹配标签，自由生成 ====================

TASK_DECOMPOSE_FREE_BRANCHED_PROMPT = """
你是一个专业的医疗临床路径规划助手（Commander LLM）。
你的任务是：根据输入的医患对话，分析其中的临床意图，生成一个**带条件分支**的Task列表。

## 可用Task类型：
- patient_profile, examination_order, exam_execution, prescription, diagnostic, schedule
- treatment_execution, notification, result_review, admission_discharge
- recovery_advice, archive

## 输出格式：
合法JSON数组，数组中每个元素可以是以下两种之一：

### 1. 普通Task
{{
  "task_type": "...",
  "summary": "该任务的简要描述",
  "depends_on": [],
  "priority": "routine",
  "params": {{...}}
}}

### 2. 条件分支节点（必须至少包含一个）
{{
  "type": "branch",
  "condition": "条件变量（如 diagnostic.primary_diagnosis）",
  "branches": [
    {{
      "condition_value": "分支条件值",
      "tasks": [普通Task, ...]
    }}
  ],
  "else_tasks": [普通Task, ...]
}}

## 要求：
1. 必须包含至少一个条件分支节点
2. 分支的condition可以基于诊断结果（diagnostic.primary_diagnosis）或检查执行结果（exam_execution.result）
3. 不同分支应覆盖不同的诊断可能性或检查结果差异
4. 当某个分支内执行了exam_execution后，可以嵌套一个基于检查结果的子分支来决定后续操作
5. 分支外的通用Task（如patient_profile、result_review）正常列出

## 当前医患对话：
{dialogue}

请输出合法JSON数组，不要包含任何额外解释文字。
"""

# ==================== 原始线性分解提示词（保留备用） ====================

TASK_DECOMPOSE_PROMPT = """
你是一个专业的医疗临床路径规划助手（Commander LLM）。
你的任务是：根据输入的原始医患对话，分析其中的临床意图，并将其分解为一个结构化的Task列表。

## 可用的Task类型如下：
- patient_profile     : 提取并整理患者基本信息与病历（SOAP格式）
- examination_order   : 申请检查项目（血常规/X光/心电图等）
- exam_execution      : 执行检查操作并自动生成模拟检查数据
- prescription        : 开具药物处方
- diagnostic          : 诊断评估与鉴别诊断
- schedule            : 制定诊疗计划与科室路由
- treatment_execution : 执行具体治疗操作（输液/手术/换药等）
- notification        : 发送通知（医生/护士/患者家属）
- result_review       : 回读并解读检查结果
- admission_discharge : 办理入院/出院/转科
- recovery_advice     : 生成康复与随访建议
- archive             : 归档至EHR/RAG数据库

## 输出要求：
请以合法JSON数组格式输出Task列表，每个Task包含以下字段：
- task_type: 任务类型（必填，取值范围见上）
- summary: 该任务的简要描述（必填）
- depends_on: 依赖的前置task_type列表（无依赖填[]）
- priority: 优先级，"urgent"/"routine"/"elective"（必填）
- params: 该任务特有参数字典（根据任务类型填写，可为{{}}）

## 示例输出：
[
  {{
    "task_type": "patient_profile",
    "summary": "从对话中提取患者基本信息，生成SOAP格式病历",
    "depends_on": [],
    "priority": "routine",
    "params": {{
      "fields": ["主诉", "现病史", "既往史", "过敏史"],
      "output_format": "SOAP"
    }}
  }},
  {{
    "task_type": "examination_order",
    "summary": "申请血常规和血钾检查",
    "depends_on": ["patient_profile"],
    "priority": "urgent",
    "params": {{
      "exam_items": ["血常规", "血钾"],
      "target_department": "检验科",
      "reason": "疑似低血钾"
    }}
  }}
]

## 当前输入的医患对话：
{dialogue}

请输出JSON数组，不要包含任何额外解释文字。
"""


CPL_GENERATE_PROMPT = """
你是一个专业的临床路径脚本生成器。
你的任务是：根据输入的Task列表，生成一段结构化的CPL（Clinical Pathway Language）脚本。

## CPL语法规则：
- PATHWAY "名称": 定义整条临床路径
- ASSERT <条件>, "<说明>": 执行前置断言
- STEP <编号> "<描述>": 定义执行步骤
- EXECUTE agent.<任务类型>(参数): 调用对应Agent
- IF/ELIF/ELSE: 条件分支

- NOTIFY <对象>(message="<内容>"): 发送通知
- LOG "<内容>" LEVEL <INFO/WARNING/ERROR>: 记录日志

## 置信度要求：
当路径中包含diagnostic步骤时，必须在诊断完成后添加置信度校验：
    IF diagnostic.confidence < 0.6:
        LOG "诊断置信度偏低，建议人工复核" LEVEL WARNING
        NOTIFY doctor.primary(message="AI诊断置信度低于阈值，请复核")

## 示例CPL片段：
PATHWAY "门诊处理路径":
    ASSERT patient.consent == True, "患者未签署知情同意"
    
    STEP 1 "生成病历":
        medical_record = EXECUTE agent.patient_profile(
            fields=["主诉", "现病史", "既往史"],
            output_format="SOAP"
        )
        LOG "病历生成完成" LEVEL INFO

    STEP 2 "检查申请与执行":
        exam_order = EXECUTE agent.examination_order(
            exam_items=["血常规", "影像检查"],
            priority="urgent"
        )
        exam_data = EXECUTE agent.exam_execution(
            exam_items=["血常规", "影像检查"],
            data_mode="auto_generate"
        )
        LOG "检查数据已生成" LEVEL INFO

    STEP 3 "AI诊断":
        diagnostic = EXECUTE agent.diagnostic(
            input=exam_data,
            rag_context=AUTO
        )
        IF diagnostic.confidence < 0.6:
            LOG "诊断置信度偏低，建议人工复核" LEVEL WARNING
            NOTIFY doctor.primary(message="AI诊断置信度低于阈值，请复核")
        LOG "诊断完成" LEVEL INFO

    STEP 4 "根据检查结果分支处理":
        IF exam_data.abnormal == True:
            NOTIFY doctor.primary(message="检查结果异常，需进一步处理")
        ELSE:
            LOG "检查结果正常" LEVEL INFO

## 当前Task列表（JSON）：
{task_list_json}

请生成完整CPL脚本，保持缩进规范，不要包含任何额外解释文字。
"""

