# cpl/interpreter.py
"""
CPL Interpreter：解析CPL脚本，提取有序的Agent调用序列

职责：
  1. 解析CPL脚本文本 → 结构化的 AgentCall 序列
  2. 保留STEP编号、依赖关系、参数等元信息
  3. 输出可直接交给 LLMPool executor 调度执行的调用计划

支持两种输入：
  - CPL脚本文本（字符串） → interpret()
  - CPLScript对象（来自generator） → interpret_script()
"""

import os
import re
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from commander.task_schema import TaskType
from .models import CPLScript, CPLNode


# ==================== CPL agent名 → TaskType 映射 ====================

_AGENT_NAME_TO_TASK_TYPE: dict[str, TaskType] = {
    "patient_profile":      TaskType.PATIENT_PROFILE,
    "examination_order":    TaskType.EXAMINATION_ORDER,
    "prescription":         TaskType.PRESCRIPTION,
    "diagnostic":           TaskType.DIAGNOSTIC,
    "schedule":             TaskType.SCHEDULE,
    "treatment_execution":  TaskType.TREATMENT_EXECUTION,
    "notification":         TaskType.NOTIFICATION,
    "result_review":        TaskType.RESULT_REVIEW,
    "admission_discharge":  TaskType.ADMISSION_DISCHARGE,
    "recovery_advice":      TaskType.RECOVERY_ADVICE,
    "archive":              TaskType.ARCHIVE,
}


class CallType(Enum):
    """调用类型"""
    AGENT    = "agent"       # agent.xxx() 调用 → 需要LLMPool调度
    PROTOCOL = "protocol"    # protocol.xxx → 标准化操作（当前记录，不调LLM）
    RAG      = "rag"         # rag.archive() → 归档操作
    EXAM     = "exam"        # exam.xxx() → 检查操作


@dataclass
class AgentCall:
    """
    一次Agent调用的完整描述（Interpreter输出的最小执行单元）

    executor模块接收AgentCall列表，逐条调度执行
    """
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int = 0                # 来源STEP编号
    step_label: str = ""                # 来源STEP描述
    call_type: CallType = CallType.AGENT
    task_type: TaskType | None = None   # 映射到的TaskType（agent调用时有值）
    agent_name: str = ""                # CPL中的原始agent名，如 "agent.patient_profile"
    variable_name: str = ""             # 返回值变量名，如 "medical_record"（无赋值时为空）
    params: dict = field(default_factory=dict)   # 调用参数
    depends_on_steps: list[int] = field(default_factory=list)  # 依赖的STEP编号
    source_line: str = ""               # 原始CPL文本行（审计用）
    is_awaited: bool = False            # 是否有AWAIT前置

    # 执行阶段由executor填写
    transaction_id: str = ""
    status: str = "pending"             # pending / running / done / failed / skipped
    result: str = ""                    # 执行结果
    error: str = ""                     # 错误信息
    started_at: str = ""
    finished_at: str = ""


@dataclass
class LogEntry:
    """CPL LOG语句"""
    step_number: int
    message: str
    level: str = "INFO"                 # INFO / WARNING / ERROR


@dataclass
class NotifyEntry:
    """CPL NOTIFY语句"""
    step_number: int
    target: str                         # doctor.primary / nurse.duty 等
    message: str


@dataclass
class AssertEntry:
    """CPL ASSERT语句"""
    condition: str
    error_message: str


@dataclass
class ExecutionPlan:
    """
    CPL Interpreter的完整输出：一个可执行的计划

    包含：
      - pathway_name: 路径名称
      - asserts: 前置断言列表
      - calls: 有序的AgentCall列表（核心，交给executor执行）
      - logs: LOG语句列表（executor执行时按顺序输出）
      - notifications: NOTIFY语句列表
    """
    pathway_name: str = ""
    asserts: list[AssertEntry] = field(default_factory=list)
    calls: list[AgentCall] = field(default_factory=list)
    logs: list[LogEntry] = field(default_factory=list)
    notifications: list[NotifyEntry] = field(default_factory=list)

    def agent_calls_only(self) -> list[AgentCall]:
        """只返回需要LLMPool调度的agent类型调用"""
        return [c for c in self.calls if c.call_type == CallType.AGENT and c.task_type is not None]

    def summary(self) -> str:
        agent_count = len(self.agent_calls_only())
        return (
            f"[ExecutionPlan] pathway={self.pathway_name} | "
            f"asserts={len(self.asserts)} | "
            f"agent_calls={agent_count} | "
            f"total_calls={len(self.calls)} | "
            f"logs={len(self.logs)} | "
            f"notifications={len(self.notifications)}"
        )

    def export_logs(self):
        """将解析出的LOG语句导出到 memory/cpl_log/ 目录"""
        if not self.logs:
            return
        cpl_log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory", "cpl_log"
        )
        os.makedirs(cpl_log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = (self.pathway_name.replace(" ", "_").replace("/", "_")
                     if self.pathway_name else "unnamed")
        filepath = os.path.join(cpl_log_dir, f"{ts}_{safe_name}.json")
        data = {
            "pathway_name": self.pathway_name,
            "exported_at": datetime.now().isoformat(),
            "total_logs": len(self.logs),
            "logs": [
                {
                    "step_number": log.step_number,
                    "level": log.level,
                    "message": log.message,
                }
                for log in self.logs
            ],
            "notifications": [
                {
                    "step_number": n.step_number,
                    "target": n.target,
                    "message": n.message,
                }
                for n in self.notifications
            ],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[CPLInterpreter] CPL日志已导出: {filepath}")


# ==================== 正则模式 ====================

# PATHWAY "名称":
_RE_PATHWAY = re.compile(r'PATHWAY\s+"([^"]+)"')

# ASSERT condition, "message"
_RE_ASSERT = re.compile(r'ASSERT\s+(.+?),\s*"([^"]*)"')

# STEP 1 "描述":
_RE_STEP = re.compile(r'STEP\s+(\d+)\s+"([^"]+)"')

# var = EXECUTE agent.xxx(...)  或  EXECUTE agent.xxx(...)
_RE_EXECUTE_ASSIGN = re.compile(
    r'(\w+)\s*=\s*EXECUTE\s+(agent|protocol|rag|exam)\.(\w+)\s*\('
)
_RE_EXECUTE_BARE = re.compile(
    r'EXECUTE\s+(agent|protocol|rag|exam)\.(\w+)\s*\(?'
)

# 多行EXECUTE闭合：检测右括号
_RE_PAREN_CLOSE = re.compile(r'^\s*\)\s*$')

# LOG "message" LEVEL INFO
_RE_LOG = re.compile(r'LOG\s+"([^"]+)"(?:\s+LEVEL\s+(\w+))?')

# NOTIFY target(message="...")
_RE_NOTIFY = re.compile(r'NOTIFY\s+([\w.]+)\s*\(\s*message\s*=\s*"([^"]+)"\s*\)')

# AWAIT var
_RE_AWAIT = re.compile(r'AWAIT\s+(\w+)')

# 参数行：key=value 或 key="value" 或 key=[...]
_RE_PARAM = re.compile(r'(\w+)\s*=\s*(.+)')


class CPLInterpreter:
    """
    CPL脚本解释器

    使用方式：
        interpreter = CPLInterpreter()

        # 从CPL文本解析
        plan = interpreter.interpret(cpl_text)

        # 从CPLScript对象解析（更直接）
        plan = interpreter.interpret_script(cpl_script)

        # 获取agent调用序列
        for call in plan.agent_calls_only():
            print(call.task_type, call.params)
    """

    # ==================== 入口1：从CPLScript对象解析 ====================

    def interpret_script(self, script: CPLScript) -> ExecutionPlan:
        """
        从CPLGenerator产出的CPLScript对象直接提取执行计划
        比文本解析更可靠（无需正则匹配）
        """
        plan = ExecutionPlan(pathway_name=script.pathway_name)

        # 解析ASSERT
        for assert_line in script.asserts:
            m = _RE_ASSERT.search(assert_line)
            if m:
                plan.asserts.append(AssertEntry(
                    condition=m.group(1).strip(),
                    error_message=m.group(2),
                ))

        # 解析STEP节点
        for node in script.nodes:
            self._parse_node_lines(node, plan)

        # 解析收尾语句
        self._parse_loose_lines(script.epilogue_lines, step_number=0, plan=plan)

        print(f"[CPLInterpreter] {plan.summary()}")
        plan.export_logs()
        return plan

    # ==================== 入口2：从CPL文本解析 ====================

    def interpret(self, cpl_text: str) -> ExecutionPlan:
        """
        从CPL脚本文本解析出执行计划
        支持CPLGenerator.render()或LLM生成的CPL文本
        """
        plan = ExecutionPlan()
        lines = cpl_text.split("\n")

        current_step = 0
        current_step_label = ""
        current_step_lines: list[str] = []
        in_step = False
        pending_await: str | None = None

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            # PATHWAY
            m = _RE_PATHWAY.search(stripped)
            if m:
                plan.pathway_name = m.group(1)
                i += 1
                continue

            # ASSERT
            m = _RE_ASSERT.search(stripped)
            if m:
                plan.asserts.append(AssertEntry(
                    condition=m.group(1).strip(),
                    error_message=m.group(2),
                ))
                i += 1
                continue

            # STEP开始
            m = _RE_STEP.search(stripped)
            if m:
                # 先处理前一个STEP积累的行
                if in_step and current_step_lines:
                    node = CPLNode(
                        step_number=current_step,
                        label=current_step_label,
                        task_id="",
                        task_type="",
                        body_lines=current_step_lines,
                    )
                    self._parse_node_lines(node, plan)
                current_step = int(m.group(1))
                current_step_label = m.group(2)
                current_step_lines = []
                in_step = True
                i += 1
                continue

            # STEP内的行
            if in_step:
                current_step_lines.append(stripped)

            i += 1

        # 处理最后一个STEP
        if in_step and current_step_lines:
            node = CPLNode(
                step_number=current_step,
                label=current_step_label,
                task_id="",
                task_type="",
                body_lines=current_step_lines,
            )
            self._parse_node_lines(node, plan)

        print(f"[CPLInterpreter] {plan.summary()}")
        plan.export_logs()
        return plan

    # ==================== 节点行解析 ====================

    def _parse_node_lines(self, node: CPLNode, plan: ExecutionPlan):
        """解析一个CPLNode的body_lines，提取AgentCall / LOG / NOTIFY"""
        pending_await = False
        i = 0
        lines = node.body_lines

        while i < len(lines):
            line = lines[i].strip()

            # AWAIT
            m = _RE_AWAIT.match(line)
            if m:
                pending_await = True
                i += 1
                continue

            # EXECUTE（带赋值）
            m = _RE_EXECUTE_ASSIGN.match(line)
            if m:
                var_name = m.group(1)
                call_domain = m.group(2)   # agent / protocol / rag / exam
                func_name = m.group(3)
                # 收集多行参数
                params, consumed = self._collect_params(lines, i)
                call = self._build_call(
                    step_number=node.step_number,
                    step_label=node.label,
                    call_domain=call_domain,
                    func_name=func_name,
                    var_name=var_name,
                    params=params,
                    source_line=line,
                    is_awaited=pending_await,
                )
                plan.calls.append(call)
                pending_await = False
                i += consumed
                continue

            # EXECUTE（无赋值）
            m = _RE_EXECUTE_BARE.match(line)
            if m:
                call_domain = m.group(1)
                func_name = m.group(2)
                params, consumed = self._collect_params(lines, i)
                call = self._build_call(
                    step_number=node.step_number,
                    step_label=node.label,
                    call_domain=call_domain,
                    func_name=func_name,
                    var_name="",
                    params=params,
                    source_line=line,
                    is_awaited=pending_await,
                )
                plan.calls.append(call)
                pending_await = False
                i += consumed
                continue

            # LOG
            m = _RE_LOG.match(line)
            if m:
                plan.logs.append(LogEntry(
                    step_number=node.step_number,
                    message=m.group(1),
                    level=m.group(2) or "INFO",
                ))
                i += 1
                continue

            # NOTIFY
            m = _RE_NOTIFY.match(line)
            if m:
                plan.notifications.append(NotifyEntry(
                    step_number=node.step_number,
                    target=m.group(1),
                    message=m.group(2),
                ))
                i += 1
                continue

            # 其他行（IF/ELIF/ELSE/ASSERT内嵌）跳过
            i += 1

    def _parse_loose_lines(self, lines: list[str], step_number: int, plan: ExecutionPlan):
        """解析非STEP内的散行（收尾区域）"""
        node = CPLNode(
            step_number=step_number,
            label="epilogue",
            task_id="",
            task_type="",
            body_lines=lines,
        )
        self._parse_node_lines(node, plan)

    # ==================== 参数收集 ====================

    def _collect_params(self, lines: list[str], start: int) -> tuple[dict, int]:
        """
        从EXECUTE行开始，收集多行参数直到遇到闭合括号
        返回 (params_dict, consumed_line_count)
        """
        params = {}
        # 检查是否第一行就闭合了（单行调用）
        first_line = lines[start].strip()
        if first_line.endswith(")") and "(" in first_line:
            # 单行调用，从括号内提取参数
            paren_content = first_line[first_line.index("(") + 1 : first_line.rindex(")")]
            params = self._parse_params_str(paren_content)
            return params, 1

        # 多行：逐行收集直到 )
        consumed = 1
        for j in range(start + 1, len(lines)):
            line = lines[j].strip()
            consumed += 1
            if _RE_PAREN_CLOSE.match(line) or line == ")":
                break
            # 参数行
            m = _RE_PARAM.match(line.rstrip(","))
            if m:
                key = m.group(1)
                val = m.group(2).strip().rstrip(",")
                params[key] = self._parse_value(val)
        return params, consumed

    def _parse_params_str(self, s: str) -> dict:
        """解析单行参数字符串如 'input=dialogue, rag_context=AUTO'"""
        params = {}
        # 简单按逗号分割（不处理嵌套逗号的情况，CPL参数一般简单）
        for part in re.split(r',\s*(?=\w+=)', s):
            part = part.strip()
            if not part:
                continue
            m = _RE_PARAM.match(part)
            if m:
                params[m.group(1)] = self._parse_value(m.group(2).strip())
        return params

    @staticmethod
    def _parse_value(val: str):
        """解析参数值：JSON列表/字典、字符串、布尔值、数字、标识符"""
        val = val.strip().rstrip(",")
        # JSON列表或字典
        if (val.startswith("[") and val.endswith("]")) or \
           (val.startswith("{") and val.endswith("}")):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
        # 字符串
        if val.startswith('"') and val.endswith('"'):
            return val[1:-1]
        # 布尔值
        if val == "True":
            return True
        if val == "False":
            return False
        # 数字
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            pass
        # 标识符（如AUTO, NONE, 变量名）
        return val

    # ==================== 构建AgentCall ====================

    def _build_call(
        self, step_number: int, step_label: str,
        call_domain: str, func_name: str, var_name: str,
        params: dict, source_line: str, is_awaited: bool
    ) -> AgentCall:
        """构建一个AgentCall对象"""
        # 确定调用类型
        call_type_map = {
            "agent": CallType.AGENT,
            "protocol": CallType.PROTOCOL,
            "rag": CallType.RAG,
            "exam": CallType.EXAM,
        }
        call_type = call_type_map.get(call_domain, CallType.AGENT)

        # 映射TaskType
        task_type = None
        if call_type == CallType.AGENT:
            task_type = _AGENT_NAME_TO_TASK_TYPE.get(func_name)

        return AgentCall(
            step_number=step_number,
            step_label=step_label,
            call_type=call_type,
            task_type=task_type,
            agent_name=f"{call_domain}.{func_name}",
            variable_name=var_name,
            params=params,
            source_line=source_line,
            is_awaited=is_awaited,
        )
