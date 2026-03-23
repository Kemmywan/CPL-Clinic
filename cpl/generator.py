# cpl/generator.py
"""
CPL Generator：将Commander产出的Task列表确定性地转换为CPL脚本

与commander_llm.py中LLM驱动的generate_cpl互补：
  - LLM方式：灵活但不可控，适合探索性生成
  - 本模块：规则驱动、确定性强、可审计，适合生产环境
"""

import json
from datetime import datetime
from collections import defaultdict

from commander.task_schema import (
    BaseTask, TaskType, TaskStatus,
    PatientProfileTask, ExaminationOrderTask, ExamExecutionTask,
    PrescriptionTask, DiagnosticTask, ScheduleTask,
    TreatmentExecutionTask, NotificationTask,
    ResultReviewTask, AdmissionDischargeTask,
    RecoveryAdviceTask, ArchiveTask,
    BranchNode,
)
from .models import CPLNode, CPLScript


# ==================== TaskType → CPL变量名 映射 ====================

_VARIABLE_NAMES = {
    TaskType.PATIENT_PROFILE:       "medical_record",
    TaskType.EXAMINATION_ORDER:     "exam_order",
    TaskType.EXAM_EXECUTION:         "exam_data",
    TaskType.PRESCRIPTION:          "prescription",
    TaskType.DIAGNOSTIC:            "diagnostic",
    TaskType.SCHEDULE:              "schedule",
    TaskType.TREATMENT_EXECUTION:   "treatment",
    TaskType.RESULT_REVIEW:         "exam_result",
    TaskType.ADMISSION_DISCHARGE:   "admission",
    TaskType.RECOVERY_ADVICE:       "recovery",
    TaskType.NOTIFICATION:          None,   # 无返回值
    TaskType.ARCHIVE:               None,   # 无返回值
}

# ==================== TaskType → STEP默认标签 ====================

_STEP_LABELS = {
    TaskType.PATIENT_PROFILE:       "生成病历",
    TaskType.EXAMINATION_ORDER:     "检查申请",
    TaskType.EXAM_EXECUTION:         "检查执行",
    TaskType.PRESCRIPTION:          "开具处方",
    TaskType.DIAGNOSTIC:            "AI诊断",
    TaskType.SCHEDULE:              "诊疗计划",
    TaskType.TREATMENT_EXECUTION:   "执行治疗",
    TaskType.RESULT_REVIEW:         "检查结果回读",
    TaskType.NOTIFICATION:          "发送通知",
    TaskType.ADMISSION_DISCHARGE:   "入出院管理",
    TaskType.RECOVERY_ADVICE:       "康复建议",
    TaskType.ARCHIVE:               "归档",
}


class CPLGenerator:
    """
    确定性CPL脚本生成器

    使用方式：
        generator = CPLGenerator()
        cpl_text = generator.render(tasks, pathway_name="门诊处理路径")
    """

    # ==================== 对外接口 ====================

    def generate(self, tasks: list, pathway_name: str | None = None) -> CPLScript:
        """
        Task列表 → CPLScript结构化对象

        支持两种输入：
        - list[BaseTask]：线性Task列表（原有行为）
        - list[BaseTask | BranchNode]：含条件分支的Task列表

        Args:
            tasks:          Commander.decompose()产出的Task列表
            pathway_name:   路径名称（默认自动生成）
        """
        if not tasks:
            return CPLScript(pathway_name=pathway_name or "空路径")

        # 检测是否包含分支节点
        has_branch = any(isinstance(item, BranchNode) for item in tasks)
        if has_branch:
            return self._generate_branched(tasks, pathway_name)

        # 原有线性生成逻辑
        return self._generate_linear(tasks, pathway_name)

    def _generate_linear(self, tasks: list[BaseTask], pathway_name: str | None = None) -> CPLScript:
        """原有线性Task列表 → CPLScript"""
        if not tasks:
            return CPLScript(pathway_name=pathway_name or "空路径")

        # 拓扑排序（按依赖关系）
        sorted_tasks = self._topological_sort(tasks)

        # 生成ASSERT
        asserts = self._generate_asserts(sorted_tasks)

        # 逐Task生成STEP节点
        nodes = []
        archive_tasks = []
        for step_num, task in enumerate(sorted_tasks, start=1):
            # Archive单独放收尾
            if task.task_type == TaskType.ARCHIVE:
                archive_tasks.append(task)
                continue
            node = self._task_to_node(task, step_num)
            nodes.append(node)

        # 重新编号（archive被抽走后连续编号）
        for i, node in enumerate(nodes, start=1):
            node.step_number = i

        # 收尾语句
        epilogue = self._generate_epilogue(archive_tasks)

        return CPLScript(
            pathway_name=pathway_name or self._infer_pathway_name(sorted_tasks),
            asserts=asserts,
            nodes=nodes,
            epilogue_lines=epilogue,
        )

    def render(self, tasks: list, pathway_name: str | None = None) -> str:
        """Task列表 → CPL脚本字符串（一步到位）"""
        script = self.generate(tasks, pathway_name)
        return script.render()

    # ==================== 带分支的生成 ====================

    def _generate_branched(self, items: list, pathway_name: str | None = None) -> CPLScript:
        """
        含BranchNode的Task列表 → CPLScript
        按原始顺序遍历，BaseTask生成普通STEP，BranchNode生成含IF/ELIF/ELSE的STEP
        """
        from commander.task_schema import flatten_tasks

        flat_tasks = flatten_tasks(items)
        asserts = self._generate_asserts(flat_tasks)

        nodes = []
        archive_tasks = []
        step_num = 0

        for item in items:
            if isinstance(item, BranchNode):
                step_num += 1
                node = self._branch_to_node(item, step_num)
                nodes.append(node)
            elif isinstance(item, BaseTask):
                if item.task_type == TaskType.ARCHIVE:
                    archive_tasks.append(item)
                    continue
                step_num += 1
                node = self._task_to_node(item, step_num)
                nodes.append(node)

        epilogue = self._generate_epilogue(archive_tasks)

        return CPLScript(
            pathway_name=pathway_name or self._infer_pathway_name(flat_tasks),
            asserts=asserts,
            nodes=nodes,
            epilogue_lines=epilogue,
        )

    def _branch_to_node(self, branch: BranchNode, step_num: int) -> CPLNode:
        """将BranchNode转换为含IF/ELIF/ELSE的CPLNode（支持嵌套分支）"""
        body_lines = []

        for i, (cond_value, branch_tasks) in enumerate(branch.branches):
            keyword = "IF" if i == 0 else "ELIF"
            body_lines.append(f'{keyword} {branch.condition} == "{cond_value}":')
            for task in branch_tasks:
                if isinstance(task, BranchNode):
                    nested_lines = self._render_nested_branch(task, indent=4)
                    body_lines.extend(nested_lines)
                else:
                    task_lines = self._get_task_body_lines(task)
                    for line in task_lines:
                        body_lines.append(f"    {line}")

        if branch.else_tasks:
            body_lines.append("ELSE:")
            for task in branch.else_tasks:
                if isinstance(task, BranchNode):
                    nested_lines = self._render_nested_branch(task, indent=4)
                    body_lines.extend(nested_lines)
                else:
                    task_lines = self._get_task_body_lines(task)
                    for line in task_lines:
                        body_lines.append(f"    {line}")

        return CPLNode(
            step_number=step_num,
            label="条件分支处理",
            task_id="",
            task_type="branch",
            body_lines=body_lines,
            depends_on=[],
        )

    def _render_nested_branch(self, branch: BranchNode, indent: int) -> list[str]:
        """递归渲染嵌套BranchNode为缩进的CPL行"""
        prefix = " " * indent
        lines = []

        for i, (cond_value, branch_tasks) in enumerate(branch.branches):
            keyword = "IF" if i == 0 else "ELIF"
            lines.append(f'{prefix}{keyword} {branch.condition} == "{cond_value}":')
            for task in branch_tasks:
                if isinstance(task, BranchNode):
                    nested = self._render_nested_branch(task, indent + 4)
                    lines.extend(nested)
                else:
                    task_lines = self._get_task_body_lines(task)
                    for line in task_lines:
                        lines.append(f"{prefix}    {line}")

        if branch.else_tasks:
            lines.append(f"{prefix}ELSE:")
            for task in branch.else_tasks:
                if isinstance(task, BranchNode):
                    nested = self._render_nested_branch(task, indent + 4)
                    lines.extend(nested)
                else:
                    task_lines = self._get_task_body_lines(task)
                    for line in task_lines:
                        lines.append(f"{prefix}    {line}")

        return lines

        return CPLNode(
            step_number=step_num,
            label="条件分支处理",
            task_id="",
            task_type="branch",
            body_lines=body_lines,
            depends_on=[],
        )

    def _get_task_body_lines(self, task: BaseTask) -> list[str]:
        """获取单个Task的CPL代码行（复用emit方法）"""
        emitter = {
            TaskType.PATIENT_PROFILE:       self._emit_patient_profile,
            TaskType.EXAMINATION_ORDER:     self._emit_examination_order,
            TaskType.EXAM_EXECUTION:        self._emit_exam_execution,
            TaskType.PRESCRIPTION:          self._emit_prescription,
            TaskType.DIAGNOSTIC:            self._emit_diagnostic,
            TaskType.SCHEDULE:              self._emit_schedule,
            TaskType.TREATMENT_EXECUTION:   self._emit_treatment_execution,
            TaskType.NOTIFICATION:          self._emit_notification,
            TaskType.RESULT_REVIEW:         self._emit_result_review,
            TaskType.ADMISSION_DISCHARGE:   self._emit_admission_discharge,
            TaskType.RECOVERY_ADVICE:       self._emit_recovery_advice,
        }
        emit_fn = emitter.get(task.task_type, self._emit_generic)
        return emit_fn(task)

    # ==================== 拓扑排序 ====================

    def _topological_sort(self, tasks: list[BaseTask]) -> list[BaseTask]:
        """按depends_on拓扑排序，无依赖的按原始顺序保持"""
        id_to_task = {t.task_id: t for t in tasks}
        in_degree = defaultdict(int)
        adjacency = defaultdict(list)

        task_ids = set(id_to_task.keys())
        for t in tasks:
            in_degree.setdefault(t.task_id, 0)
            for dep_id in (t.depends_on or []):
                if dep_id in task_ids:
                    adjacency[dep_id].append(t.task_id)
                    in_degree[t.task_id] += 1

        # BFS（Kahn算法），保持原始顺序稳定性
        queue = [t.task_id for t in tasks if in_degree[t.task_id] == 0]
        result = []
        while queue:
            current = queue.pop(0)
            result.append(id_to_task[current])
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 若有环（理论上不应该），追加剩余
        visited = {t.task_id for t in result}
        for t in tasks:
            if t.task_id not in visited:
                result.append(t)

        return result

    # ==================== ASSERT 生成 ====================

    def _generate_asserts(self, tasks: list[BaseTask]) -> list[str]:
        """根据Task列表生成前置ASSERT语句"""
        asserts = []
        has_treatment = any(
            t.task_type == TaskType.TREATMENT_EXECUTION for t in tasks
        )
        if has_treatment:
            asserts.append('ASSERT patient.consent == True, "患者未签署知情同意"')

        has_prescription = any(
            t.task_type == TaskType.PRESCRIPTION for t in tasks
        )
        if has_prescription:
            for t in tasks:
                if t.task_type == TaskType.PRESCRIPTION and getattr(t, 'contraindication_check', False):
                    asserts.append('ASSERT patient.allergies != UNSET, "过敏史信息缺失，无法开具处方"')
                    break
        return asserts

    # ==================== 单Task → CPLNode ====================

    def _task_to_node(self, task: BaseTask, step_num: int) -> CPLNode:
        """将单个Task转换为CPLNode"""
        emitter = {
            TaskType.PATIENT_PROFILE:       self._emit_patient_profile,
            TaskType.EXAMINATION_ORDER:     self._emit_examination_order,
            TaskType.EXAM_EXECUTION:        self._emit_exam_execution,
            TaskType.PRESCRIPTION:          self._emit_prescription,
            TaskType.DIAGNOSTIC:            self._emit_diagnostic,
            TaskType.SCHEDULE:              self._emit_schedule,
            TaskType.TREATMENT_EXECUTION:   self._emit_treatment_execution,
            TaskType.NOTIFICATION:          self._emit_notification,
            TaskType.RESULT_REVIEW:         self._emit_result_review,
            TaskType.ADMISSION_DISCHARGE:   self._emit_admission_discharge,
            TaskType.RECOVERY_ADVICE:       self._emit_recovery_advice,
        }

        emit_fn = emitter.get(task.task_type, self._emit_generic)
        body_lines = emit_fn(task)

        label = _STEP_LABELS.get(task.task_type, task.task_type.value)

        return CPLNode(
            step_number=step_num,
            label=label,
            task_id=task.task_id,
            task_type=task.task_type.value,
            body_lines=body_lines,
            depends_on=task.depends_on or [],
        )

    # ==================== 各TaskType的CPL代码发射器 ====================

    def _emit_patient_profile(self, task: PatientProfileTask) -> list[str]:
        lines = []
        fields = getattr(task, 'fields', []) or ["主诉", "现病史", "既往史", "过敏史"]
        fmt = getattr(task, 'output_format', "SOAP")
        fields_str = json.dumps(fields, ensure_ascii=False)
        lines.append(f"medical_record = EXECUTE agent.patient_profile(")
        lines.append(f'    fields={fields_str},')
        lines.append(f'    output_format="{fmt}"')
        lines.append(f")")
        lines.append(f'LOG "病历生成完成" LEVEL INFO')
        return lines

    def _emit_examination_order(self, task: ExaminationOrderTask) -> list[str]:
        lines = []
        items = getattr(task, 'exam_items', []) or []
        priority = getattr(task, 'priority', 'routine')
        dept = getattr(task, 'target_department', '检验科')
        reason = getattr(task, 'reason', '')
        items_str = json.dumps(items, ensure_ascii=False)
        lines.append(f"exam_order = EXECUTE agent.examination_order(")
        lines.append(f"    exam_items={items_str},")
        lines.append(f'    priority="{priority}",')
        lines.append(f'    target_department="{dept}"')
        if reason:
            lines[-1] = lines[-1].rstrip(")")  # 还没结束
            lines[-1] += ","
            lines.append(f'    reason="{reason}"')
        lines.append(f")")
        if priority == "urgent":
            lines.append(f'LOG "紧急检查已申请: {items_str}" LEVEL WARNING')
        else:
            lines.append(f'LOG "检查申请完成" LEVEL INFO')
        return lines

    def _emit_exam_execution(self, task: ExamExecutionTask) -> list[str]:
        lines = []
        items = getattr(task, 'exam_items', []) or []
        items_str = json.dumps(items, ensure_ascii=False)
        lines.append(f"exam_data = EXECUTE agent.exam_execution(")
        lines.append(f"    exam_items={items_str},")
        lines.append(f'    data_mode="auto_generate"')
        lines.append(f")")
        lines.append(f'LOG "检查数据已自动生成" LEVEL INFO')
        return lines

    def _emit_prescription(self, task: PrescriptionTask) -> list[str]:
        lines = []
        meds = getattr(task, 'medications', []) or []
        route = getattr(task, 'route', '口服')
        meds_str = json.dumps(meds, ensure_ascii=False)
        lines.append(f"prescription = EXECUTE agent.prescription(")
        lines.append(f"    medications={meds_str},")
        lines.append(f'    route="{route}"')
        lines.append(f")")
        if getattr(task, 'contraindication_check', True):
            lines.append(f"ASSERT prescription.contraindication_clear == True, "
                         f'"禁忌症校验未通过，处方已拦截"')
        lines.append(f'LOG "处方开具完成" LEVEL INFO')
        return lines

    def _emit_diagnostic(self, task: DiagnosticTask) -> list[str]:
        lines = []
        rag = getattr(task, 'rag_context_used', False)
        lines.append(f"diagnostic = EXECUTE agent.diagnostic(")
        lines.append(f"    input=exam_result,")
        if rag:
            lines.append(f"    rag_context=AUTO")
        else:
            lines.append(f"    rag_context=NONE")
        lines.append(f")")
        primary = getattr(task, 'primary_diagnosis', '')
        if primary:
            lines.append(f'# 预期主诊断: {primary}')
        confidence = getattr(task, 'confidence', 0.0)
        if confidence > 0:
            lines.append(f"IF diagnostic.confidence < 0.6:")
            lines.append(f'    LOG "诊断置信度偏低，建议人工复核" LEVEL WARNING')
            lines.append(f'    NOTIFY doctor.primary(message="AI诊断置信度低于阈值，请复核")')
        lines.append(f'LOG "诊断完成" LEVEL INFO')
        return lines

    def _emit_schedule(self, task: ScheduleTask) -> list[str]:
        lines = []
        steps = getattr(task, 'planned_steps', []) or []
        duration = getattr(task, 'estimated_duration', '')
        routing = getattr(task, 'department_routing', []) or []
        lines.append(f"schedule = EXECUTE agent.schedule(")
        lines.append(f"    input=medical_record")
        lines.append(f")")
        if steps:
            steps_str = json.dumps(steps, ensure_ascii=False)
            lines.append(f"# 计划步骤: {steps_str}")
        if duration:
            lines.append(f'# 预计周期: {duration}')
        if routing:
            routing_str = json.dumps(routing, ensure_ascii=False)
            lines.append(f'# 科室路由: {routing_str}')
        lines.append(f'LOG "诊疗计划生成完成" LEVEL INFO')
        return lines

    def _emit_treatment_execution(self, task: TreatmentExecutionTask) -> list[str]:
        lines = []
        ttype = getattr(task, 'treatment_type', '')
        executor = getattr(task, 'executor_role', '主治医生')
        preconditions = getattr(task, 'preconditions', []) or []
        monitoring = getattr(task, 'monitoring_plan', '')

        for cond in preconditions:
            lines.append(f'ASSERT {_sanitize_condition(cond)}, "{cond}"')

        lines.append(f'treatment = EXECUTE agent.treatment_execution(')
        lines.append(f'    treatment_type="{ttype}",')
        lines.append(f'    executor_role="{executor}"')
        lines.append(f")")

        if monitoring:
            lines.append(f'# 监测计划: {monitoring}')

        lines.append(f'LOG "治疗执行: {ttype}" LEVEL INFO')
        return lines

    def _emit_notification(self, task: NotificationTask) -> list[str]:
        lines = []
        recipients = getattr(task, 'recipients', []) or []
        message = getattr(task, 'message', '')
        urgency = getattr(task, 'urgency', 'routine')
        channel = getattr(task, 'channel', '系统消息')
        trigger = getattr(task, 'trigger_condition', '')

        if trigger:
            lines.append(f'IF {_sanitize_condition(trigger)}:')
            for r in recipients:
                target = _to_notify_target(r)
                lines.append(f'    NOTIFY {target}(message="{message}")')
        else:
            for r in recipients:
                target = _to_notify_target(r)
                lines.append(f'NOTIFY {target}(message="{message}")')

        if urgency == "immediate":
            lines.append(f'LOG "紧急通知已发送" LEVEL WARNING')
        else:
            lines.append(f'LOG "通知已发送" LEVEL INFO')
        return lines

    def _emit_result_review(self, task: ResultReviewTask) -> list[str]:
        lines = []
        exam_ref = getattr(task, 'exam_ref', '')
        lines.append(f"exam_result = EXECUTE agent.result_review(")
        if exam_ref:
            lines.append(f'    exam_ref="{exam_ref}"')
        else:
            lines.append(f"    input=exam_order")
        lines.append(f")")

        abnormal_flags = getattr(task, 'abnormal_flags', []) or []
        if abnormal_flags:
            flags_str = json.dumps(abnormal_flags, ensure_ascii=False)
            lines.append(f"# 关注异常标记: {flags_str}")

        requires_action = getattr(task, 'requires_action', False)
        if requires_action:
            lines.append(f"IF exam_result.has_abnormal:")
            lines.append(f'    NOTIFY doctor.primary(message="检查结果异常，请关注")')
            lines.append(f'    LOG "检查结果异常" LEVEL WARNING')
        else:
            lines.append(f'LOG "检查结果回读完成" LEVEL INFO')
        return lines

    def _emit_admission_discharge(self, task: AdmissionDischargeTask) -> list[str]:
        lines = []
        action = getattr(task, 'action', 'admission')
        ward = getattr(task, 'ward', '')
        lines.append(f'admission = EXECUTE agent.admission_discharge(')
        lines.append(f'    action="{action}"')
        if ward:
            lines[-1] += ","
            lines.append(f'    ward="{ward}"')
        lines.append(f")")
        if action == "discharge":
            lines.append(f'LOG "出院手续办理完成" LEVEL INFO')
        elif action == "transfer":
            lines.append(f'LOG "转科手续办理完成" LEVEL INFO')
        else:
            lines.append(f'LOG "入院手续办理完成" LEVEL INFO')
        return lines

    def _emit_recovery_advice(self, task: RecoveryAdviceTask) -> list[str]:
        lines = []
        lines.append(f"recovery = EXECUTE agent.recovery_advice(")
        lines.append(f"    input=diagnostic")
        lines.append(f")")

        red_flags = getattr(task, 'red_flags', []) or []
        if red_flags:
            flags_str = json.dumps(red_flags, ensure_ascii=False)
            lines.append(f"# 警示症状: {flags_str}")

        follow_up = getattr(task, 'follow_up_schedule', []) or []
        if follow_up:
            schedule_str = json.dumps(follow_up, ensure_ascii=False)
            lines.append(f"# 随访计划: {schedule_str}")

        lines.append(f'LOG "康复建议生成完成" LEVEL INFO')
        return lines

    def _emit_generic(self, task: BaseTask) -> list[str]:
        """兜底：未匹配到专用emitter的TaskType"""
        var = _VARIABLE_NAMES.get(task.task_type)
        type_val = task.task_type.value
        if var:
            return [
                f'{var} = EXECUTE agent.{type_val}()',
                f'LOG "{type_val}执行完成" LEVEL INFO',
            ]
        return [
            f'EXECUTE agent.{type_val}()',
            f'LOG "{type_val}执行完成" LEVEL INFO',
        ]

    # ==================== 收尾（Archive Task）====================

    def _generate_epilogue(self, archive_tasks: list) -> list[str]:
        lines = []
        if not archive_tasks:
            lines.append('LOG "路径执行完成" LEVEL INFO')
            return lines

        for task in archive_tasks:
            targets = getattr(task, 'archive_targets', []) or []
            ehr = getattr(task, 'ehr_system', 'local')
            rag = getattr(task, 'rag_indexing', True)
            if targets:
                targets_str = ", ".join(f"{t}" for t in targets)
                lines.append(f"EXECUTE rag.archive(targets=[{targets_str}])")
            else:
                lines.append(f"EXECUTE rag.archive(")
                lines.append(f"    record=medical_record,")
                lines.append(f"    exam=exam_result,")
                lines.append(f"    diagnostic=diagnostic")
                lines.append(f")")
            if rag:
                lines.append(f'LOG "已归档至RAG向量数据库" LEVEL INFO')
            else:
                lines.append(f'LOG "已归档至EHR系统({ehr})" LEVEL INFO')

        lines.append(f'LOG "路径执行完成，已归档" LEVEL INFO')
        return lines

    # ==================== 路径名推断 ====================

    def _infer_pathway_name(self, tasks: list[BaseTask]) -> str:
        """从Task列表推断一个合理的路径名称"""
        type_names = [t.task_type.value for t in tasks]
        if "diagnostic" in type_names and "prescription" in type_names:
            return "诊断-处方路径"
        if "diagnostic" in type_names:
            return "诊断评估路径"
        if "admission_discharge" in type_names:
            return "入出院管理路径"
        return "临床处理路径"


# ==================== 工具函数 ====================

def _to_notify_target(recipient: str) -> str:
    """将中文接收方映射为CPL标识符"""
    mapping = {
        "主治医生": "doctor.primary",
        "值班护士": "nurse.duty",
        "护士": "nurse.duty",
        "患者家属": "patient.family",
        "患者": "patient",
        "医生": "doctor.primary",
    }
    return mapping.get(recipient, f'recipient("{recipient}")')


def _sanitize_condition(text: str) -> str:
    """
    将自然语言条件转为CPL风格的伪条件表达式
    用于ASSERT/IF中（保留可读性，不做真正的解析）
    """
    # 若已经像代码表达式则直接返回
    if any(op in text for op in ("==", "!=", "<", ">", ">=", "<=")):
        return text
    # 否则包装为字符串条件
    return f'condition("{text}")'
