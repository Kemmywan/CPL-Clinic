# ambient/multimodal_adapter.py
from .models import RawClinicalData, InputSource, InputModality
from .text_input import TextInputAdapter


class MultimodalAdapter:
    """
    统一多模态输入标准化接口（Ambient Sensing Module核心）

    职责：
      - 屏蔽不同输入来源/模态的差异
      - 对外统一暴露 ingest() 系列方法
      - 返回标准化的 RawClinicalData 对象，交给Commander层处理

    当前支持：TEXT（文件/API字符串）
    预留扩展：AUDIO（音频转写）、REALTIME（实时流）
    """

    def __init__(self):
        self._text_adapter = TextInputAdapter()
        # self._audio_adapter = AudioInputAdapter()  # 预留，未来扩展

    # ==================== 统一对外接口 ====================

    def ingest_from_file(self, path: str) -> RawClinicalData:
        """
        从本地文件读取（自动判断txt/json格式）
        返回单条 RawClinicalData
        """
        ext = path.rsplit('.', 1)[-1].lower()
        if ext in ('txt',):
            data = self._text_adapter.from_txt_file(path)
        elif ext in ('json',):
            # json文件场景：取第一条（单次推理）
            data = next(self._text_adapter.from_json_file(path))
        else:
            # 未知扩展名，暴力作为txt处理
            data = self._text_adapter.from_txt_file(path)

        self._validate_and_log(data)
        return data

    def ingest_batch_from_json(self, path: str, dialogue_key: str = "dialogue"):
        """
        从json文件批量读取（对应test_record.py的batch实验场景）
        逐条yield RawClinicalData
        """
        for data in self._text_adapter.from_json_file(path, dialogue_key):
            self._validate_and_log(data)
            yield data

    def ingest_from_string(self, text: str) -> RawClinicalData:
        """
        从字符串直接创建（对应前端API传入场景）
        """
        data = self._text_adapter.from_string(text)
        self._validate_and_log(data)
        return data

    # ==================== 预留多模态扩展 ====================

    def ingest_from_audio(self, audio_path: str) -> RawClinicalData:
        """
        【预留】音频输入，转写后标准化
        未来接入 Whisper/FunASR 等语音转写模型
        """
        raise NotImplementedError(
            "音频输入模块尚未实现。"
            "计划接入：Whisper / FunASR / Azure Speech"
        )

    def ingest_realtime_stream(self, stream):
        """
        【预留】实时音频流输入
        对应论文 Ambient Sensing Module 的完整形态
        """
        raise NotImplementedError("实时流输入尚未实现")

    # ==================== 内部工具 ====================

    @staticmethod
    def _validate_and_log(data: RawClinicalData):
        if not data.is_valid():
            raise ValueError("RawClinicalData内容为空，无法继续处理")
        print(f"[Ambient] {data.summary()}")
