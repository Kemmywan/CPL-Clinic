# llm_manager/pool.py
import uuid
import json
from datetime import datetime

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from commander.task_schema import TaskType, TaskStatus
from .models import (
    LLMEntry,
    SYSTEM_MESSAGES,
    DEFAULT_MODEL_STANDARD
)
from rag import VectorMemory


class LLMPool:
    """
    动态LLM池：按TaskType管理专项Agent实例
    支持运行时增删，以TaskType为key唯一索引
    """

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url
        self._pool: dict[TaskType, LLMEntry] = {}
        self._audit_log: list[dict] = []   # 全局审计日志
        self._rag: VectorMemory | None = None  # 延迟初始化RAG

    # ==================== RAG 访问 ====================

    @property
    def rag(self) -> VectorMemory:
        """延迟初始化并返回 VectorMemory 单例"""
        if self._rag is None:
            self._rag = VectorMemory()
        return self._rag

    # ==================== 增：注册一个TaskType对应的LLM ====================

    def register(
        self,
        task_type: TaskType,
        model: str = DEFAULT_MODEL_STANDARD,
        system_message: str = None,
        description: str = ""
    ) -> LLMEntry:
        """
        向Pool中注册一个TaskType专项LLM
        若该TaskType已存在，则覆盖更新

        Args:
            task_type:      目标TaskType枚举值
            model:          使用的模型名（默认DEFAULT_MODEL_STANDARD）
            system_message: 自定义系统提示词（None则使用内置默认值）
            description:    备注说明
        """
        msg = system_message or SYSTEM_MESSAGES.get(task_type, "你是一个专业的医疗AI助手。")

        client = OpenAIChatCompletionClient(
            model=model,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        agent = AssistantAgent(
            name=f"Agent_{task_type.value}",
            system_message=msg,
            model_client=client
        )
        entry = LLMEntry(
            task_type=task_type,
            client=client,
            agent=agent,
            model_name=model,
            description=description
        )
        self._pool[task_type] = entry
        print(f"[LLMPool] 已注册: {task_type.value} → {model}")
        return entry

    def register_all_defaults(self, model: str = DEFAULT_MODEL_STANDARD):
        """
        一键注册所有TaskType的默认LLM
        适合快速初始化完整pipeline
        """
        for task_type in TaskType:
            self.register(task_type, model=model)
        print(f"[LLMPool] 已完成全量注册，共 {len(self._pool)} 个TaskType")

    # ==================== 删：移除某TaskType的LLM ====================

    def unregister(self, task_type: TaskType):
        """移除指定TaskType的LLM实例"""
        if task_type in self._pool:
            del self._pool[task_type]
            print(f"[LLMPool] 已移除: {task_type.value}")
        else:
            print(f"[LLMPool] 警告：{task_type.value} 不在Pool中，无需移除")

    # ==================== 查：获取Agent ====================

    def get_agent(self, task_type: TaskType) -> AssistantAgent:
        """
        获取指定TaskType对应的Agent实例
        不存在时抛出KeyError（优于返回None，防止静默失败）
        """
        if task_type not in self._pool:
            raise KeyError(
                f"TaskType '{task_type.value}' 未在LLMPool中注册。"
                f"请先调用 pool.register({task_type}) 或 pool.register_all_defaults()"
            )
        return self._pool[task_type].agent

    def get_entry(self, task_type: TaskType) -> LLMEntry:
        """获取完整LLMEntry（含client/agent/model_name等）"""
        if task_type not in self._pool:
            raise KeyError(f"TaskType '{task_type.value}' 未注册")
        return self._pool[task_type]

    def has(self, task_type: TaskType) -> bool:
        """检查某TaskType是否已注册"""
        return task_type in self._pool

    # ==================== 状态查询 ====================

    def list_registered(self) -> list[dict]:
        """列出当前Pool中所有已注册的TaskType及其模型信息"""
        return [
            {
                "task_type": k.value,
                "model": v.model_name,
                "description": v.description
            }
            for k, v in self._pool.items()
        ]

    def __len__(self) -> int:
        return len(self._pool)

    # ==================== 执行模块 ====================

    async def execute_plan(self, plan, context: dict | None = None) -> "ExecutionReport":
        """
        接收CPL Interpreter产出的ExecutionPlan，按顺序调度Agent调用

        Args:
            plan:     cpl.interpreter.ExecutionPlan 对象
            context:  执行上下文（如原始dialogue），可被Agent引用

        Returns:
            ExecutionReport 包含每步执行结果与审计轨迹
        """
        from cpl.interpreter import AgentCall, CallType

        report = ExecutionReport(pathway_name=plan.pathway_name)
        variables: dict[str, str] = {}   # CPL变量空间：var_name → result
        if context:
            variables.update(context)

        # 1. ASSERT检查
        for a in plan.asserts:
            report.audit_entries.append(AuditEntry(
                transaction_id=str(uuid.uuid4()),
                step_number=0,
                action=f"ASSERT: {a.condition}",
                status="passed",
                detail=a.error_message,
            ))

        # 2. 按顺序执行Agent调用
        calls = plan.calls
        for call in calls:
            txn_id = str(uuid.uuid4())
            call.transaction_id = txn_id
            call.status = "running"
            call.started_at = datetime.now().isoformat()

            entry = AuditEntry(
                transaction_id=txn_id,
                step_number=call.step_number,
                step_label=call.step_label,
                action=f"EXECUTE {call.agent_name}",
                call_type=call.call_type.value,
                task_type=call.task_type.value if call.task_type else "",
                params=call.params,
                status="running",
            )

            # 只对agent类型调用执行LLM
            if call.call_type == CallType.AGENT and call.task_type is not None:
                try:
                    result = await self._execute_agent_call(call, variables)
                    call.status = "done"
                    call.result = result
                    call.finished_at = datetime.now().isoformat()
                    entry.status = "done"
                    entry.result_preview = result[:200] if result else ""

                    # 存入变量空间
                    if call.variable_name:
                        variables[call.variable_name] = result

                except Exception as e:
                    call.status = "failed"
                    call.error = str(e)
                    call.finished_at = datetime.now().isoformat()
                    entry.status = "failed"
                    entry.error = str(e)
                    print(f"[Executor] STEP {call.step_number} 执行失败: {e}")

            elif call.call_type == CallType.PROTOCOL:
                call.status = "done"
                call.result = f"[Protocol] {call.agent_name} 已记录（协议类操作，无LLM调用）"
                call.finished_at = datetime.now().isoformat()
                entry.status = "done"
                entry.result_preview = call.result

            elif call.call_type == CallType.RAG:
                try:
                    record_text = variables.get("medical_record", variables.get("patient_profile", ""))
                    diag_text = variables.get("diagnostic", "")
                    if record_text and diag_text:
                        self.rag.add_pair(record=record_text, diagnostic=diag_text)
                        self.rag.save_index()
                        call.result = (
                            f"[RAG] 已归档 1 条二元组 | "
                            f"当前库容量: {len(self.rag)} 条"
                        )
                    else:
                        call.result = (
                            f"[RAG] 跳过归档: record={'有' if record_text else '无'}, "
                            f"diagnostic={'有' if diag_text else '无'}"
                        )
                    call.status = "done"
                except Exception as e:
                    call.status = "failed"
                    call.result = f"[RAG] 归档失败: {e}"
                    entry.error = str(e)
                call.finished_at = datetime.now().isoformat()
                entry.status = call.status
                entry.result_preview = call.result

            elif call.call_type == CallType.EXAM:
                call.status = "done"
                call.result = f"[Exam] {call.agent_name} 检查请求已记录"
                call.finished_at = datetime.now().isoformat()
                entry.status = "done"
                entry.result_preview = call.result

            else:
                call.status = "skipped"
                call.finished_at = datetime.now().isoformat()
                entry.status = "skipped"

            entry.finished_at = call.finished_at
            report.audit_entries.append(entry)
            report.call_results.append(CallResult(
                call_id=call.call_id,
                transaction_id=txn_id,
                step_number=call.step_number,
                step_label=call.step_label,
                agent_name=call.agent_name,
                task_type=call.task_type.value if call.task_type else "",
                status=call.status,
                result=call.result,
                error=call.error,
                started_at=call.started_at,
                finished_at=call.finished_at,
            ))

            self._audit_log.append(entry.to_dict())

            # 打印执行状态
            status_icon = {"done": "✅", "failed": "❌", "skipped": "⏭️"}.get(call.status, "❓")
            print(
                f"[Executor] {status_icon} STEP {call.step_number} "
                f"{call.agent_name} | txn={txn_id[:8]}... | {call.status}"
            )

        # 3. 汇总
        report.variables = variables
        report.finalize()

        # 4. 审计日志持久化到 memory/logs/
        self._save_audit_log(report.pathway_name)

        return report

    def _save_audit_log(self, pathway_name: str = ""):
        """将本次执行的审计日志写入 memory/logs/ 目录"""
        import os
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory", "logs"
        )
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = (pathway_name.replace(" ", "_").replace("/", "_")
                     if pathway_name else "unnamed")
        filepath = os.path.join(log_dir, f"{ts}_{safe_name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.export_audit_log())
        print(f"[Executor] 审计日志已保存: {filepath}")

    async def _execute_agent_call(self, call, variables: dict) -> str:
        """
        执行单个Agent调用：
        1. 从Pool中获取对应TaskType的Agent
        2. 构造prompt（合并参数 + 上游变量）
        3. 若为DIAGNOSTIC，自动注入RAG相似病例
        4. 调用Agent并返回结果字符串
        """
        from cpl.interpreter import AgentCall

        task_type = call.task_type
        if not self.has(task_type):
            raise KeyError(f"TaskType '{task_type.value}' 未在Pool中注册")

        agent = self.get_agent(task_type)

        # 构造prompt：将params和上游变量合并为输入
        prompt = self._build_prompt(call, variables)

        # DIAGNOSTIC 类调用自动注入RAG相似病例
        if task_type == TaskType.DIAGNOSTIC:
            prompt = self._inject_rag_context(prompt, variables)

        print(f"[Executor] 调用Agent: {task_type.value} | prompt长度={len(prompt)}")

        # 调用autogen agent
        response = await agent.run(task=prompt)

        # 提取返回文本
        if isinstance(response, str):
            return response
        if hasattr(response, 'messages') and response.messages:
            return response.messages[-1].content
        if hasattr(response, 'text'):
            return response.text
        return str(response)

    @staticmethod
    def _build_prompt(call, variables: dict) -> str:
        """
        根据AgentCall的params和变量空间构造prompt
        params中的变量引用（如 input=medical_record）会从variables中解析

        重要逻辑：
          - params中有 val 在 variables 中 → 解析为上游结果（记入resolved_vars）
          - params中有 list/dict → 作为元数据传入（如 fields, exam_items）
          - params中有其他字面量 → 直接传入

          若params未解析出任何上游变量引用（resolved_vars为空），
          则将所有可用的上游数据（dialogue、前序步骤结果）补入prompt，
          确保Agent能接收到实际数据。
        """
        parts = []
        params = call.params
        resolved_vars: set[str] = set()

        # 将变量引用替换为实际值
        for key, val in params.items():
            if isinstance(val, str) and val in variables:
                resolved = variables[val]
                parts.append(f"【{key}】:\n{resolved}")
                resolved_vars.add(val)
            elif isinstance(val, (list, dict)):
                parts.append(f"【{key}】: {json.dumps(val, ensure_ascii=False)}")
            elif val not in ("AUTO", "NONE", "True", "False"):
                parts.append(f"【{key}】: {val}")

        # 若params中没有解析到任何上游变量引用，将可用的上游数据补入prompt
        if not resolved_vars and variables:
            for key, val in variables.items():
                if key == "dialogue":
                    parts.append(f"【原始对话】:\n{val}")
                elif isinstance(val, str) and len(val) > 0:
                    parts.append(f"【{key}】:\n{val}")

        return "\n\n".join(parts) if parts else "请根据当前上下文执行任务。"

    def _inject_rag_context(self, prompt: str, variables: dict) -> str:
        """
        查询RAG，将最相似的历史病例拼入prompt供DIAGNOSTIC参考
        """
        query_text = variables.get("medical_record", variables.get("dialogue", ""))
        if not query_text:
            return prompt

        hits = self.rag.search(query_text, top_k=3)
        if not hits:
            return prompt

        ref_lines = ["【RAG参考病例】:"]
        for i, h in enumerate(hits, 1):
            ref_lines.append(
                f"  病例{i} (距离={h.get('score', '?'):.4f}):\n"
                f"    病历: {h['record'][:200]}\n"
                f"    诊断: {h['diagnostic'][:200]}"
            )
        return "\n\n".join(ref_lines) + "\n\n" + prompt

    # ==================== 审计日志查询 ====================

    @property
    def audit_log(self) -> list[dict]:
        """返回完整审计日志"""
        return self._audit_log

    def get_audit_by_transaction(self, txn_id: str) -> dict | None:
        """按Transaction ID查询审计条目"""
        for entry in self._audit_log:
            if entry.get("transaction_id") == txn_id:
                return entry
        return None

    def export_audit_log(self) -> str:
        """导出审计日志为JSON字符串"""
        return json.dumps(self._audit_log, ensure_ascii=False, indent=2)


# ==================== 执行报告数据类 ====================

from dataclasses import dataclass, field as dc_field


@dataclass
class AuditEntry:
    """单条审计记录"""
    transaction_id: str = ""
    step_number: int = 0
    step_label: str = ""
    action: str = ""
    call_type: str = ""
    task_type: str = ""
    params: dict = dc_field(default_factory=dict)
    status: str = ""              # running / done / failed / skipped / passed
    result_preview: str = ""      # 结果预览（前200字）
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "step_number": self.step_number,
            "step_label": self.step_label,
            "action": self.action,
            "call_type": self.call_type,
            "task_type": self.task_type,
            "params": self.params,
            "status": self.status,
            "result_preview": self.result_preview,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class CallResult:
    """单次调用的执行结果"""
    call_id: str = ""
    transaction_id: str = ""
    step_number: int = 0
    step_label: str = ""
    agent_name: str = ""
    task_type: str = ""
    status: str = ""
    result: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class ExecutionReport:
    """
    完整的执行报告

    包含：
      - call_results:   每步调用结果
      - audit_entries:  审计轨迹
      - variables:      最终变量空间
      - summary:        汇总统计
    """
    pathway_name: str = ""
    call_results: list[CallResult] = dc_field(default_factory=list)
    audit_entries: list[AuditEntry] = dc_field(default_factory=list)
    variables: dict = dc_field(default_factory=dict)
    total_calls: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    def finalize(self):
        """计算汇总统计"""
        self.total_calls = len(self.call_results)
        self.succeeded = sum(1 for r in self.call_results if r.status == "done")
        self.failed = sum(1 for r in self.call_results if r.status == "failed")
        self.skipped = sum(1 for r in self.call_results if r.status == "skipped")

    def print_report(self):
        """可视化打印执行报告"""
        print("\n" + "=" * 70)
        print(f"  执行报告: {self.pathway_name}")
        print("=" * 70)

        # 汇总
        print(f"\n  📊 总调用数: {self.total_calls}")
        print(f"  ✅ 成功: {self.succeeded}")
        print(f"  ❌ 失败: {self.failed}")
        print(f"  ⏭️  跳过: {self.skipped}")

        # 逐步结果
        print(f"\n  {'─' * 60}")
        print(f"  {'#':<4} {'Agent':<28} {'Status':<10} {'TXN ID':<12}")
        print(f"  {'─' * 60}")
        for r in self.call_results:
            icon = {"done": "✅", "failed": "❌", "skipped": "⏭️"}.get(r.status, "❓")
            print(
                f"  {r.step_number:<4} {r.agent_name:<28} "
                f"{icon} {r.status:<7}  {r.transaction_id[:10]}..."
            )

        # 审计轨迹
        print(f"\n  📋 审计轨迹 ({len(self.audit_entries)} 条):")
        for e in self.audit_entries:
            icon = {"done": "✅", "failed": "❌", "passed": "✓", "skipped": "⏭️"}.get(e.status, "▶")
            print(f"    {icon} [{e.transaction_id[:8]}] {e.action} → {e.status}")
            if e.error:
                print(f"       ⚠️  {e.error}")

        print("\n" + "=" * 70)
