# commander/task_schema.py
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid

class TaskType(Enum):
    PATIENT_PROFILE       = "patient_profile"
    EXAMINATION_ORDER     = "examination_order"
    PRESCRIPTION          = "prescription"
    DIAGNOSTIC            = "diagnostic"
    SCHEDULE              = "schedule"
    TREATMENT_EXECUTION   = "treatment_execution"
    NOTIFICATION          = "notification"
    RESULT_REVIEW         = "result_review"
    ADMISSION_DISCHARGE   = "admission_discharge"
    RECOVERY_ADVICE       = "recovery_advice"
    ARCHIVE               = "archive"

class TaskStatus(Enum):
    PENDING   = "pending"    # 待执行
    RUNNING   = "running"    # 执行中
    DONE      = "done"       # 已完成
    FAILED    = "failed"     # 执行失败
    OVERRIDDEN = "overridden" # 已被医生覆写

@dataclass
class BaseTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    transaction_id: str = ""          # 审计用
    depends_on: list = field(default_factory=list)  # 依赖的前置task_id列表
    override_log: list = field(default_factory=list) # 医生覆写记录
    cpl_ref: str = ""                 # 关联的CPL脚本节点ID

    def mark_overridden(self, field_name: str, old_val, new_val, operator: str):
        """记录医生覆写操作"""
        self.status = TaskStatus.OVERRIDDEN
        self.override_log.append({
            "timestamp": datetime.now().isoformat(),
            "field": field_name,
            "old_value": old_val,
            "new_value": new_val,
            "operator": operator
        })

@dataclass
class PatientProfileTask(BaseTask):
    task_type = TaskType.PATIENT_PROFILE
    # 从对话/历史记录中提取并结构化患者基本信息
    fields: list = field(default_factory=list)  # 需要提取的字段，如["主诉","现病史","既往史","过敏史"]
    source_dialogue: str = ""  # 原始对话文本
    output_format: str = "SOAP"  # SOAP / 自由文本 / 结构化JSON

@dataclass
class ExaminationOrderTask(BaseTask):
    task_type = TaskType.EXAMINATION_ORDER
    exam_items: list = field(default_factory=list)  # ["血常规", "血钾", "胸部X光", "心电图"]
    priority: str = ""           # "urgent" / "routine" / "stat"
    reason: str = ""             # 申请理由（关联诊断）
    target_department: str = ""  # 目标科室，如"检验科"/"影像科"

@dataclass
class PrescriptionTask(BaseTask):
    task_type = TaskType.PRESCRIPTION
    medications: list = field(default_factory=list)  # [{"name":"阿莫西林","dose":"0.5g","freq":"TID","duration":"7天"}]
    route: str = ""              # "口服" / "静脉注射" / "外用"
    pharmacy_instruction: str = ""  # 取药/用药说明
    contraindication_check: bool = True  # 是否触发禁忌症校验

@dataclass
class DiagnosticTask(BaseTask):
    task_type = TaskType.DIAGNOSTIC
    differential_diagnoses: list = field(default_factory=list)  # 鉴别诊断列表（LLM生成候选）
    primary_diagnosis: str = ""         # 主诊断
    evidence_refs: list = field(default_factory=list)  # 支撑诊断的检查结果或症状依据
    rag_context_used: bool = False # 是否引用了RAG历史案例
    confidence: float = 0.0        # LLM置信度（0~1）

@dataclass
class ScheduleTask(BaseTask):
    task_type = TaskType.SCHEDULE
    planned_steps: list = field(default_factory=list)  # 有序诊疗步骤列表
    estimated_duration: str = ""   # 预计周期，如"住院3天"/"门诊随访2周"
    department_routing: list = field(default_factory=list)  # 涉及科室流转，如["急诊","心内科","检验科"]
    priority: str = ""             # "elective" / "urgent" / "emergency"

@dataclass
class TreatmentExecutionTask(BaseTask):
    task_type = TaskType.TREATMENT_EXECUTION
    treatment_type: str = ""    # "手术" / "输液" / "换药" / "物理治疗"
    protocol_ref: str = ""      # 引用的标准协议名，如"protocol.potassium_supplement"
    executor_role: str = ""     # "主治医生" / "护士" / "技师"
    preconditions: list = field(default_factory=list)  # 执行前提条件，如["患者已签知情同意","血压稳定"]
    monitoring_plan: str = ""   # 执行中监测计划

@dataclass
class NotificationTask(BaseTask):
    task_type = TaskType.NOTIFICATION
    recipients: list = field(default_factory=list)  # ["主治医生", "值班护士", "患者家属"]
    message: str = ""           # 通知内容
    urgency: str = ""           # "immediate" / "routine"
    channel: str = ""           # "系统消息" / "短信" / "呼叫系统"
    trigger_condition: str = "" # 触发条件，如"血钾<3.5时通知"

@dataclass
class ResultReviewTask(BaseTask):
    task_type = TaskType.RESULT_REVIEW
    exam_ref: str = ""          # 关联的ExaminationOrderTask ID
    result_data: dict = field(default_factory=dict)  # 检查结果数值，如{"serum_potassium": 3.2}
    interpretation: str = ""    # LLM自动解读（如"血钾偏低，建议补钾"）
    abnormal_flags: list = field(default_factory=list)  # 异常标记列表
    requires_action: bool = False  # 是否需要触发后续任务

@dataclass
class AdmissionDischargeTask(BaseTask):
    task_type = TaskType.ADMISSION_DISCHARGE
    action: str = ""            # "admission" / "discharge" / "transfer"
    ward: str = ""              # 目标病房/科室
    discharge_summary: str = "" # 出院摘要（LLM生成）
    follow_up_plan: str = ""    # 出院后随访计划
    instructions: list = field(default_factory=list)  # 出院医嘱列表

@dataclass
class RecoveryAdviceTask(BaseTask):
    task_type = TaskType.RECOVERY_ADVICE
    lifestyle_recommendations: list = field(default_factory=list)  # 生活方式建议
    dietary_restrictions: list = field(default_factory=list)       # 饮食禁忌
    medication_continuation: list = field(default_factory=list)    # 出院后继续用药
    follow_up_schedule: list = field(default_factory=list)         # 随访时间节点
    red_flags: list = field(default_factory=list)                  # 需紧急返诊的警示症状

@dataclass
class ArchiveTask(BaseTask):
    task_type = TaskType.ARCHIVE
    archive_targets: list = field(default_factory=list)  # 归档对象列表（哪些Task结果需要写入EHR/RAG）
    ehr_system: str = ""           # 目标EHR系统标识
    rag_indexing: bool = True      # 是否同步写入RAG向量数据库
    audit_trail: list = field(default_factory=list)  # 审计轨迹（每步transaction ID链）



