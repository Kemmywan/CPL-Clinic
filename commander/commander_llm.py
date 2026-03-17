# commander/commander_llm.py
import json
import uuid
from datetime import datetime
from ambient.models import RawClinicalData
from .task_schema import (
    BaseTask, TaskType, TaskStatus,
    PatientProfileTask, ExaminationOrderTask,
    PrescriptionTask, DiagnosticTask, ScheduleTask,
    TreatmentExecutionTask, NotificationTask,
    ResultReviewTask, AdmissionDischargeTask,
    RecoveryAdviceTask, ArchiveTask
)
from .prompts import TASK_DECOMPOSE_PROMPT, CPL_GENERATE_PROMPT


# ==================== Task工厂：JSON → 具体Task对象 ====================

class TaskFactory:
    """
    将Commander LLM输出的JSON条目
    实例化为对应的具体Task dataclass对象
    """

    @classmethod
    def build(cls, item: dict, depends_map: dict) -> BaseTask:
        """
        根据task_type字符串，实例化对应Task对象
        depends_map: {task_type_str -> task_id} 用于解析depends_on为task_id列表
        """
        try:
            task_type = TaskType(item["task_type"])
        except (ValueError, KeyError):
            raise ValueError(f"未知的TaskType: {item.get('task_type', 'MISSING')}")

        # _BUILDERS在类方法中通过cls引用，避免类定义时静态方法未绑定的坑
        builders = {
            TaskType.PATIENT_PROFILE:      cls._build_patient_profile,
            TaskType.EXAMINATION_ORDER:    cls._build_examination_order,
            TaskType.PRESCRIPTION:         cls._build_prescription,
            TaskType.DIAGNOSTIC:           cls._build_diagnostic,
            TaskType.SCHEDULE:             cls._build_schedule,
            TaskType.TREATMENT_EXECUTION:  cls._build_treatment_execution,
            TaskType.NOTIFICATION:         cls._build_notification,
            TaskType.RESULT_REVIEW:        cls._build_result_review,
            TaskType.ADMISSION_DISCHARGE:  cls._build_admission_discharge,
            TaskType.RECOVERY_ADVICE:      cls._build_recovery_advice,
            TaskType.ARCHIVE:              cls._build_archive,
        }

        builder = builders.get(task_type)
        if not builder:
            raise NotImplementedError(f"TaskFactory尚未实现builder: {task_type}")

        params = item.get("params", {})
        depends_on = [
            depends_map[dep]
            for dep in item.get("depends_on", [])
            if dep in depends_map
        ]
        task = builder(params, depends_on, item.get("summary", ""))
        task.task_type = task_type
        return task

    # ==================== 各类型Builder ====================

    @staticmethod
    def _build_patient_profile(params, depends_on, summary):
        return PatientProfileTask(
            fields=params.get("fields", ["主诉", "现病史", "既往史", "过敏史"]),
            source_dialogue=params.get("source_dialogue", ""),
            output_format=params.get("output_format", "SOAP"),
            depends_on=depends_on
        )

    @staticmethod
    def _build_examination_order(params, depends_on, summary):
        return ExaminationOrderTask(
            exam_items=params.get("exam_items", []),
            priority=params.get("priority", "routine"),
            reason=params.get("reason", summary),
            target_department=params.get("target_department", "检验科"),
            depends_on=depends_on
        )

    @staticmethod
    def _build_prescription(params, depends_on, summary):
        return PrescriptionTask(
            medications=params.get("medications", []),
            route=params.get("route", "口服"),
            pharmacy_instruction=params.get("pharmacy_instruction", ""),
            contraindication_check=params.get("contraindication_check", True),
            depends_on=depends_on
        )

    @staticmethod
    def _build_diagnostic(params, depends_on, summary):
        return DiagnosticTask(
            differential_diagnoses=params.get("differential_diagnoses", []),
            primary_diagnosis=params.get("primary_diagnosis", ""),
            evidence_refs=params.get("evidence_refs", []),
            rag_context_used=params.get("rag_context_used", False),
            confidence=params.get("confidence", 0.0),
            depends_on=depends_on
        )

    @staticmethod
    def _build_schedule(params, depends_on, summary):
        return ScheduleTask(
            planned_steps=params.get("planned_steps", []),
            estimated_duration=params.get("estimated_duration", ""),
            department_routing=params.get("department_routing", []),
            priority=params.get("priority", "routine"),
            depends_on=depends_on
        )

    @staticmethod
    def _build_treatment_execution(params, depends_on, summary):
        return TreatmentExecutionTask(
            treatment_type=params.get("treatment_type", ""),
            protocol_ref=params.get("protocol_ref", ""),
            executor_role=params.get("executor_role", "主治医生"),
            preconditions=params.get("preconditions", []),
            monitoring_plan=params.get("monitoring_plan", ""),
            depends_on=depends_on
        )

    @staticmethod
    def _build_notification(params, depends_on, summary):
        return NotificationTask(
            recipients=params.get("recipients", []),
            message=params.get("message", summary),
            urgency=params.get("urgency", "routine"),
            channel=params.get("channel", "系统消息"),
            trigger_condition=params.get("trigger_condition", ""),
            depends_on=depends_on
        )

    @staticmethod
    def _build_result_review(params, depends_on, summary):
        return ResultReviewTask(
            exam_ref=params.get("exam_ref", ""),
            result_data=params.get("result_data", {}),
            interpretation=params.get("interpretation", ""),
            abnormal_flags=params.get("abnormal_flags", []),
            requires_action=params.get("requires_action", False),
            depends_on=depends_on
        )

    @staticmethod
    def _build_admission_discharge(params, depends_on, summary):
        return AdmissionDischargeTask(
            action=params.get("action", "admission"),
            ward=params.get("ward", ""),
            discharge_summary=params.get("discharge_summary", ""),
            follow_up_plan=params.get("follow_up_plan", ""),
            instructions=params.get("instructions", []),
            depends_on=depends_on
        )

    @staticmethod
    def _build_recovery_advice(params, depends_on, summary):
        return RecoveryAdviceTask(
            lifestyle_recommendations=params.get("lifestyle_recommendations", []),
            dietary_restrictions=params.get("dietary_restrictions", []),
            medication_continuation=params.get("medication_continuation", []),
            follow_up_schedule=params.get("follow_up_schedule", []),
            red_flags=params.get("red_flags", []),
            depends_on=depends_on
        )

    @staticmethod
    def _build_archive(params, depends_on, summary):
        return ArchiveTask(
            archive_targets=params.get("archive_targets", []),
            ehr_system=params.get("ehr_system", "local"),
            rag_indexing=params.get("rag_indexing", True),
            audit_trail=params.get("audit_trail", []),
            depends_on=depends_on
        )


# ==================== Commander LLM 核心 ====================

class CommanderLLM:
    """
    Commander LLM：AutoCLP的大脑与调度器

    职责：
      1. 接收 RawClinicalData
      2. 调用LLM进行意图识别与任务分解 → Task列表
      3. 将Task列表形式化为CPL脚本字符串
    """

    def __init__(self, agent):
        """
        agent: 来自LLMManager的Commander专用LLM实例
               建议使用能力最强的模型，它是整个pipeline的调度核心
        """
        self.agent = agent
        self.factory = TaskFactory()

    # ==================== Step 1: 任务分解 ====================

    async def decompose(self, raw_data: RawClinicalData) -> list[BaseTask]:
        """
        输入：RawClinicalData
        输出：Task对象列表（已实例化的具体Task子类）
        """
        print(f"[Commander] 开始任务分解，输入长度：{len(raw_data.content)} 字符")

        prompt = TASK_DECOMPOSE_PROMPT.format(dialogue=raw_data.content)
        raw_response = await self._call_llm(prompt)

        # 解析LLM输出的JSON
        task_items = self._parse_json_response(raw_response)

        # 构建 task_type → task_id 映射（用于depends_on解析）
        depends_map = {}
        tasks = []
        for item in task_items:
            task = TaskFactory.build(item, depends_map)
            depends_map[item["task_type"]] = task.task_id
            tasks.append(task)
            print(f"[Commander] 生成Task: {task.task_type.value} | id={task.task_id[:8]}...")

        print(f"[Commander] 任务分解完成，共 {len(tasks)} 个Task")
        return tasks

    # ==================== Step 2: CPL生成 ====================

    async def generate_cpl(self, tasks: list[BaseTask]) -> str:
        """
        输入：Task对象列表
        输出：CPL脚本字符串（供医生审阅/覆写，再交CPL Interpreter执行）
        """
        print(f"[Commander] 开始生成CPL脚本，Task数量：{len(tasks)}")

        # 将Task列表序列化为JSON供LLM参考
        tasks_json = json.dumps(
            [self._task_to_dict(t) for t in tasks],
            ensure_ascii=False,
            indent=2
        )
        prompt = CPL_GENERATE_PROMPT.format(tasks_json=tasks_json)
        cpl_script = await self._call_llm(prompt)

        # 清理LLM可能输出的markdown代码块包裹
        cpl_script = self._clean_cpl_output(cpl_script)

        print(f"[Commander] CPL脚本生成完成，长度：{len(cpl_script)} 字符")
        return cpl_script

    # ==================== Step 1+2 一体化入口 ====================

    async def process(self, raw_data: RawClinicalData) -> tuple[list[BaseTask], str]:
        """
        一体化入口：
        RawClinicalData → Task列表 + CPL脚本
        返回 (tasks, cpl_script) 供下游CPL Interpreter消费
        """
        tasks = await self.decompose(raw_data)
        cpl_script = await self.generate_cpl(tasks)
        return tasks, cpl_script

    # ==================== 内部工具方法 ====================

    async def _call_llm(self, prompt: str) -> str:
        """
        调用Commander LLM，返回原始字符串响应
        兼容autogen/openai风格的agent调用接口
        """
        try:
            # 适配你现有的agent调用方式
            response = await self.agent.run(task=prompt)
            # 若response是对象，提取text字段；若已是字符串直接返回
            if isinstance(response, str):
                return response
            if hasattr(response, 'messages') and response.messages:
                return response.messages[-1].content
            if hasattr(response, 'text'):
                return response.text
            return str(response)
        except Exception as e:
            raise RuntimeError(f"[Commander] LLM调用失败：{e}")

    @staticmethod
    def _parse_json_response(raw: str) -> list[dict]:
        """
        从LLM响应中提取合法JSON数组
        健壮处理：自动去除markdown代码块包裹/多余文字
        """
        # 尝试提取```json...```或```...```代码块
        import re
        pattern = r'```(?:json)?\s*([\s\S]*?)```'
        match = re.search(pattern, raw)
        if match:
            raw = match.group(1).strip()

        # 尝试提取第一个[...]数组
        bracket_match = re.search(r'(\[[\s\S]*\])', raw)
        if bracket_match:
            raw = bracket_match.group(1).strip()

        try:
            result = json.loads(raw)
            if not isinstance(result, list):
                raise ValueError("LLM返回的JSON不是数组格式")
            return result
        except json.JSONDecodeError as e:
            raise ValueError(
                f"[Commander] LLM输出JSON解析失败：{e}\n"
                f"原始输出前200字：{raw[:200]}"
            )

    @staticmethod
    def _clean_cpl_output(raw: str) -> str:
        """
        清理CPL脚本输出中可能的markdown代码块包裹
        """
        import re
        pattern = r'```(?:cpl|python|plaintext)?\s*([\s\S]*?)```'
        match = re.search(pattern, raw)
        if match:
            return match.group(1).strip()
        return raw.strip()

    @staticmethod
    def _task_to_dict(task: BaseTask) -> dict:
        """
        将Task对象序列化为可读字典，供CPL生成prompt使用
        注意：dataclass用__dict__即可，但要过滤掉内部状态字段
        """
        d = {k: v for k, v in task.__dict__.items()
             if k not in ('override_log', 'transaction_id')}
        # TaskType/TaskStatus枚举转字符串
        if hasattr(d.get('task_type'), 'value'):
            d['task_type'] = d['task_type'].value
        if hasattr(d.get('status'), 'value'):
            d['status'] = d['status'].value
        return d
