# ambient/text_input.py
import os
import json
from .models import RawClinicalData, InputSource, InputModality


class TextInputAdapter:
    """
    文本输入适配器
    负责将以下来源统一转化为 RawClinicalData：
      1. 本地 txt 文件（单段对话）
      2. 本地 json 文件（对话数组，逐条产出）
      3. 直接传入的字符串（来自API/前端）
    """

    # ==================== 从文件读取 ====================

    def from_txt_file(self, path: str) -> RawClinicalData:
        """
        读取单个txt文件，整体内容作为一段对话
        对应你现有的 with open(args.dialogue) as f: dialogue = f.read()
        """
        self._assert_file_exists(path)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return RawClinicalData(
            content=content,
            source=InputSource.FILE,
            modality=InputModality.TEXT,
            metadata={"filename": os.path.basename(path), "path": path}
        )

    def from_json_file(self, path: str, dialogue_key: str = "dialogue"):
        """
        读取json文件（内容形如[{...},{...}]的对话数组）
        逐条yield RawClinicalData，对应你test_record.py中的batch处理逻辑
        
        Args:
            path: json文件路径
            dialogue_key: 每条记录中对话字段的key名（默认"dialogue"）
        """
        self._assert_file_exists(path)
        with open(path, 'r', encoding='utf-8') as f:
            items = json.loads(f.read())

        if not isinstance(items, list):
            raise ValueError(f"JSON文件内容应为数组格式，实际为：{type(items)}")

        for idx, item in enumerate(items):
            if dialogue_key not in item:
                raise KeyError(f"第{idx}条记录中缺少字段 '{dialogue_key}'")
            yield RawClinicalData(
                content=item[dialogue_key],
                source=InputSource.FILE,
                modality=InputModality.TEXT,
                metadata={
                    "filename": os.path.basename(path),
                    "index": idx,
                    "original_item": item   # 保留完整原始记录
                }
            )

    # ==================== 从字符串直接输入 ====================

    def from_string(self, text: str, source: InputSource = InputSource.API) -> RawClinicalData:
        """
        直接从字符串创建 RawClinicalData
        对应前端POST /run传入的dialogue字段
        """
        if not text or not text.strip():
            raise ValueError("输入对话内容不能为空")
        return RawClinicalData(
            content=text.strip(),
            source=source,
            modality=InputModality.TEXT,
            metadata={}
        )

    # ==================== 内部工具 ====================

    @staticmethod
    def _assert_file_exists(path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到输入文件：{path}")
        if not os.path.isfile(path):
            raise ValueError(f"路径不是文件：{path}")
