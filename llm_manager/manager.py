# llm_manager/manager.py
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from commander.task_schema import TaskType
from .models import (
    COMMANDER_SYSTEM_MESSAGE,
    DEFAULT_MODEL_STRONG,
    DEFAULT_MODEL_STANDARD
)
from .pool import LLMPool
import os

load_dotenv()


class LLMManager:
    """
    AutoCLP统一LLM管理器

    职责：
    1. 维护Commander LLM（强力模型，负责意图识别和任务分解）
    2. 维护LLMPool（按TaskType动态管理专项Agent）
    3. 对外暴露统一接口，屏蔽底层client/agent创建细节

    使用方式：
        llms = LLMManager()
        agent = llms.get_agent(TaskType.DIAGNOSTIC)
        commander = llms.commander_agent
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://aihubmix.com/v1",
        commander_model: str = DEFAULT_MODEL_STRONG,
        default_agent_model: str = DEFAULT_MODEL_STANDARD,
        auto_register_all: bool = True
    ):
        # ==================== API Key读取 ====================
        self._api_key = api_key or os.getenv("AIHUBMIX_API_KEY") or ""
        if not self._api_key:
            raise EnvironmentError(
                "未检测到有效的API Key，请在.env中设置AIHUBMIX_API_KEY "
                "或在初始化LLMManager时传入api_key参数"
            )

        self._base_url = base_url
        self._commander_model = commander_model
        self._default_agent_model = default_agent_model

        # ==================== 初始化Commander Client ====================
        self._commander_client = OpenAIChatCompletionClient(
            model=commander_model,
            api_key=self._api_key,
            base_url=self._base_url,
        )

        # ==================== 初始化Commander Agent ====================
        self._commander_agent = AssistantAgent(
            name="CommanderAgent",
            model_client=self._commander_client,
            system_message=COMMANDER_SYSTEM_MESSAGE,
        )

        # ==================== 初始化LLMPool ====================
        self._pool = LLMPool(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        # ==================== 自动注册全量TaskType ====================
        if auto_register_all:
            self._register_all_task_agents()

        print(
            f"[LLMManager] 初始化完成 | "
            f"Commander: {commander_model} | "
            f"Pool: {default_agent_model} | "
            f"已注册TaskType: {len(self._pool)} 个"
        )

    # ==================== 全量注册专项Agent ====================

    def _register_all_task_agents(self):
        """
        将所有TaskType对应的专项Agent批量注册进LLMPool
        每个TaskType可独立指定model，默认使用default_agent_model
        如有特殊需求（如DiagnosticTask需要强力模型），可在此处单独覆盖
        """
        task_model_map = {
            # 默认使用standard模型
            TaskType.PATIENT_PROFILE:       self._default_agent_model,
            TaskType.EXAMINATION_ORDER:     self._default_agent_model,
            TaskType.PRESCRIPTION:          self._default_agent_model,
            TaskType.SCHEDULE:              self._default_agent_model,
            TaskType.TREATMENT_EXECUTION:   self._default_agent_model,
            TaskType.NOTIFICATION:          self._default_agent_model,
            TaskType.RESULT_REVIEW:         self._default_agent_model,
            TaskType.ADMISSION_DISCHARGE:   self._default_agent_model,
            TaskType.RECOVERY_ADVICE:       self._default_agent_model,
            TaskType.ARCHIVE:               self._default_agent_model,
            # 诊断任务使用强力模型
            TaskType.DIAGNOSTIC:            self._commander_model,
        }

        for task_type, model in task_model_map.items():
            self._pool.register(task_type, model)

    # ==================== 对外接口 ====================

    @property
    def commander_agent(self) -> AssistantAgent:
        """返回Commander Agent"""
        return self._commander_agent

    def get_agent(self, task_type: TaskType) -> AssistantAgent:
        """
        按TaskType获取对应专项Agent
        如果该TaskType未注册，自动用default_agent_model注册后返回
        """
        if not self._pool.has(task_type):
            print(
                f"[LLMManager] 警告：TaskType {task_type.value} 未注册，"
                f"自动使用默认模型 {self._default_agent_model} 注册"
            )
            self._pool.register(task_type, self._default_agent_model)
        return self._pool.get_agent(task_type)

    def register_agent(
        self,
        task_type: TaskType,
        model: str = None,
        system_message: str = None
    ):
        """
        手动注册/覆盖某个TaskType的专项Agent
        适用于需要特殊配置的任务类型（如特定system prompt）
        """
        self._pool.register(
            task_type,
            model or self._default_agent_model,
            system_message=system_message
        )
        print(f"[LLMManager] 已注册/覆盖 TaskType: {task_type.value}")

    def list_registered(self) -> list:
        """返回当前已注册的所有TaskType列表"""
        return self._pool.list_registered()

    # ==================== 向后兼容旧版接口 ====================
    # 保留旧版agent_1~agent_4属性，避免main.py/server.py大规模改动
    # 后续逐步废弃，迁移到get_agent(TaskType.xxx)方式

    @property
    def agent_1(self) -> AssistantAgent:
        """病历生成Agent（向后兼容）"""
        return self.get_agent(TaskType.PATIENT_PROFILE)

    @property
    def agent_2(self) -> AssistantAgent:
        """检查计划Agent（向后兼容）"""
        return self.get_agent(TaskType.SCHEDULE)

    @property
    def agent_3(self) -> AssistantAgent:
        """诊断Agent（向后兼容）"""
        return self.get_agent(TaskType.DIAGNOSTIC)

    @property
    def agent_4(self) -> AssistantAgent:
        """康复建议Agent（向后兼容）"""
        return self.get_agent(TaskType.RECOVERY_ADVICE)

    @property
    def agent_test(self) -> AssistantAgent:
        """检查结果生成Agent - 测试用（向后兼容）"""
        return self.get_agent(TaskType.EXAMINATION_ORDER)
