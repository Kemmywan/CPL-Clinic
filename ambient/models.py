# ambient/models.py
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class InputSource(Enum):
    FILE       = "file"       # 从txt/json文件读入
    API        = "api"        # 从web前端/REST API传入
    AUDIO      = "audio"      # 音频转写（预留）
    REALTIME   = "realtime"   # 实时流式输入（预留）


class InputModality(Enum):
    TEXT       = "text"       # 纯文本对话
    AUDIO      = "audio"      # 音频（预留）
    MULTIMODAL = "multimodal" # 多模态混合（预留）


@dataclass
class RawClinicalData:
    """
    所有输入源的统一标准化数据对象
    无论来自文件/API/音频，输出给Commander层的格式完全一致
    """
    content: str                          # 原始对话文本内容（核心字段）
    source: InputSource                   # 来源类型
    modality: InputModality               # 输入模态
    timestamp: str = field(              # 采集时间戳
        default_factory=lambda: datetime.now().isoformat()
    )
    metadata: dict = field(default_factory=dict)  # 扩展元数据（文件名/语言/说话人等）

    def is_valid(self) -> bool:
        """基本有效性校验：内容非空"""
        return bool(self.content and self.content.strip())

    def summary(self) -> str:
        """便于日志输出的摘要"""
        preview = self.content[:60].replace('\n', ' ')
        return (
            f"[RawClinicalData] "
            f"source={self.source.value} | "
            f"modality={self.modality.value} | "
            f"length={len(self.content)} chars | "
            f"preview='{preview}...'"
        )
