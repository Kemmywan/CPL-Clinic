# test_task_decompose.py
"""
AutoCLP Task Decompose 测试脚本
读取指定txt中的dialogue，调用Commander LLM进行任务分解，可视化输出结果
用法: python test_task_decompose.py -d data/1.txt
"""

from cpl import CPLGenerator, CPLInterpreter
import argparse
import asyncio
import json
from dataclasses import fields as dataclass_fields

from ambient import MultimodalAdapter
from commander import CommanderLLM
from commander.task_schema import BaseTask, TaskType, TaskStatus
from llm_manager import LLMManager
from llm_manager.models import SYSTEM_MESSAGES, COMMANDER_SYSTEM_MESSAGE


# ==================== 可视化工具 ====================

PRIORITY_ICON = {"urgent": "🔴", "routine": "🟡", "elective": "🟢"}
STATUS_ICON = {
    TaskStatus.PENDING: "⏳", TaskStatus.RUNNING: "▶️",
    TaskStatus.DONE: "✅", TaskStatus.FAILED: "❌",
    TaskStatus.OVERRIDDEN: "✏️",
}


def print_banner(title: str, width: int = 70):
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_task_card(idx: int, task: BaseTask):
    """以卡片形式打印单个Task"""
    task_type = task.task_type.value if isinstance(task.task_type, TaskType) else str(task.task_type)
    status = task.status if isinstance(task.status, TaskStatus) else TaskStatus(task.status)
    priority = getattr(task, "priority", "routine")
    p_icon = PRIORITY_ICON.get(priority, "⚪")
    s_icon = STATUS_ICON.get(status, "❓")

    print(f"\n┌─ Task #{idx + 1} ─────────────────────────────────────────")
    print(f"│  类型      : {task_type}")
    print(f"│  Task ID   : {task.task_id[:12]}...")
    print(f"│  状态      : {s_icon} {status.value}")
    if hasattr(task, "priority"):
        print(f"│  优先级    : {p_icon} {priority}")
    if task.depends_on:
        deps = ", ".join(d[:8] + "..." for d in task.depends_on)
        print(f"│  依赖      : [{deps}]")
    else:
        print(f"│  依赖      : (无)")

    # 打印该Task子类特有字段
    base_field_names = {f.name for f in dataclass_fields(BaseTask)}
    for f in dataclass_fields(task):
        if f.name in base_field_names or f.name == "task_type":
            continue
        val = getattr(task, f.name, None)
        if val is None or val == "" or val == [] or val == {}:
            continue
        val_str = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
        if len(val_str) > 60:
            val_str = val_str[:57] + "..."
        print(f"│  {f.name:<12}: {val_str}")

    print(f"└───────────────────────────────────────────────────")


def print_dependency_graph(tasks: list[BaseTask]):
    """用ASCII打印简易依赖DAG"""
    id_to_name = {}
    for i, t in enumerate(tasks):
        label = f"[{i + 1}] {t.task_type.value}"
        id_to_name[t.task_id] = label

    print_banner("依赖关系图 (DAG)")
    has_dep = False
    for t in tasks:
        label = id_to_name[t.task_id]
        if t.depends_on:
            for dep_id in t.depends_on:
                parent = id_to_name.get(dep_id, dep_id[:8] + "...")
                print(f"  {parent}  ──▶  {label}")
                has_dep = True
        else:
            print(f"  (root) ──▶  {label}")
    if not has_dep:
        print("  (所有Task均无依赖，可并行执行)")


def print_summary_table(tasks: list[BaseTask]):
    """汇总表格"""
    print_banner("任务汇总表")
    header = f"  {'#':<4} {'TaskType':<24} {'Priority':<10} {'Status':<10} {'Depends':<8}"
    print(header)
    print("  " + "-" * 60)
    for i, t in enumerate(tasks):
        task_type = t.task_type.value if isinstance(t.task_type, TaskType) else str(t.task_type)
        priority = getattr(t, "priority", "-")
        status = t.status.value if isinstance(t.status, TaskStatus) else str(t.status)
        dep_count = len(t.depends_on) if t.depends_on else 0
        print(f"  {i + 1:<4} {task_type:<24} {priority:<10} {status:<10} {dep_count:<8}")


# ==================== 主流程 ====================

async def main():
    parser = argparse.ArgumentParser(description="AutoCLP Task Decompose 测试")
    parser.add_argument(
        "-d", "--dialogue",
        type=str, required=True,
        help="对话输入文件路径（txt格式）"
    )
    args = parser.parse_args()

    # 1. 读取对话
    adapter = MultimodalAdapter()
    raw_data = adapter.ingest_from_file(args.dialogue)

    print_banner("原始对话内容 (前300字)")
    preview = raw_data.content[:300].strip()
    print(f"  {preview}{'...' if len(raw_data.content) > 300 else ''}")
    print(f"\n  [总长度: {len(raw_data.content)} 字符]")

    # 2. 初始化LLM Manager + Commander
    llm_mgr = LLMManager()
    commander = CommanderLLM(agent=llm_mgr.commander_agent)

    # 2.5 输出各Agent的System Prompt
    print_banner("Commander System Prompt")
    print(f"  {COMMANDER_SYSTEM_MESSAGE[:200].strip()}...")
    print(f"  [总长度: {len(COMMANDER_SYSTEM_MESSAGE)} 字符]")

    print_banner("各TaskType Agent System Prompt")
    for task_type in TaskType:
        msg = SYSTEM_MESSAGES.get(task_type, "(无)")
        preview = msg.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        registered = "✅" if llm_mgr._pool.has(task_type) else "❌"
        entry = llm_mgr._pool.get_entry(task_type) if llm_mgr._pool.has(task_type) else None
        model = entry.model_name if entry else "-"
        print(f"  {registered} {task_type.value:<24} [{model}]")
        print(f"     {preview}")
        print()

    # 3. 任务分解
    print_banner("Commander 任务分解中...")
    tasks = await commander.decompose(raw_data)

    # 4. 可视化输出
    print_summary_table(tasks)

    print_banner("Task 详情卡片")
    for i, task in enumerate(tasks):
        print_task_card(i, task)

    print_dependency_graph(tasks)

    # 5. 统计信息
    print_banner("统计")
    type_count = {}
    for t in tasks:
        name = t.task_type.value
        type_count[name] = type_count.get(name, 0) + 1
    print(f"  总Task数:  {len(tasks)}")
    print(f"  类型分布:  {json.dumps(type_count, ensure_ascii=False)}")
    urgent = sum(1 for t in tasks if getattr(t, "priority", "") == "urgent")
    print(f"  紧急任务:  {urgent} 个")
    root_count = sum(1 for t in tasks if not t.depends_on)
    print(f"  根任务(无依赖): {root_count} 个")
    print()

    generator = CPLGenerator()
    cpl_text = generator.render(tasks, pathway_name="门诊处理路径")

    print_banner("CPL 脚本")
    print(cpl_text)

    # 6. CPL解释 → 执行计划
    interpreter = CPLInterpreter()
    script = generator.generate(tasks, pathway_name="门诊处理路径")
    plan = interpreter.interpret_script(script)

    print_banner("执行计划概览")
    print(f"  {plan.summary()}")
    print(f"\n  Agent调用序列:")
    for i, call in enumerate(plan.agent_calls_only(), 1):
        params_str = json.dumps(call.params, ensure_ascii=False) if call.params else "{}"
        if len(params_str) > 50:
            params_str = params_str[:47] + "..."
        print(f"    {i}. STEP {call.step_number} | {call.agent_name} → ${call.variable_name or '(void)'} | {params_str}")

    # 7. 调度执行
    print_banner("LLMPool 调度执行中...")
    report = await llm_mgr._pool.execute_plan(
        plan,
        context={"dialogue": raw_data.content}
    )

    # 8. 执行报告
    report.print_report()

    # 9. 打印各步骤LLM返回结果
    print_banner("各步骤执行结果")
    for r in report.call_results:
        if r.status == "done" and r.result:
            print(f"\n┌─ STEP {r.step_number} [{r.agent_name}] ──────────────────")
            print(f"│  TXN: {r.transaction_id[:12]}...")
            result_preview = r.result[:500]
            for line in result_preview.split("\n"):
                print(f"│  {line}")
            if len(r.result) > 500:
                print(f"│  ... (共 {len(r.result)} 字符)")
            print(f"└─────────────────────────────────────────────")

    # 10. RAG 信息
    pool = llm_mgr._pool
    rag = pool.rag
    print_banner("RAG 记忆库状态")
    print(f"  📦 存储路径:  {rag.pair_file}")
    print(f"  📦 索引路径:  {rag.index_file}")
    print(f"  📊 已归档条数: {len(rag)}")
    if len(rag) > 0:
        print(f"\n  最近归档的二元组:")
        for i, pair in enumerate(rag.pairs[-3:], max(1, len(rag) - 2)):
            rec_preview = pair["record"][:80].replace("\n", " ")
            diag_preview = pair["diagnostic"][:80].replace("\n", " ")
            print(f"    [{i}] 病历: {rec_preview}...")
            print(f"        诊断: {diag_preview}...")

        # 用原始对话做一次检索示例
        sample_query = raw_data.content[:200]
        hits = rag.search(sample_query, top_k=3)
        if hits:
            print(f"\n  🔍 检索示例 (query=对话前200字, top_k=3):")
            for j, h in enumerate(hits, 1):
                print(f"    {j}. 距离={h.get('score', '?'):.4f}")
                print(f"       病历: {h['record'][:60].replace(chr(10), ' ')}...")
                print(f"       诊断: {h['diagnostic'][:60].replace(chr(10), ' ')}...")


if __name__ == "__main__":
    asyncio.run(main())