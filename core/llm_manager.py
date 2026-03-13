from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
import os

load_dotenv()

api_key_get = os.getenv("AIHUBMIX_API_KEY") 
api_key: str = ""
if api_key_get != None:
    api_key = api_key_get

# SYSTEM_MESSAGES for the llm
SYSTEM_MESSAGE_1 = """你是一个专业的医疗信息提取AI助手。
你的任务是仔细阅读医生和病人之间的问诊对话，并从中提取信息，生成一份结构化的电子病历。

请务必以严格的 JSON 格式输出，必须包含以下 8 个确切的字段。如果对话中未提及某个字段的信息，请填入"未提及"：
{
    "病情描述": "",
    "希望获得的帮助": "",
    "怀孕情况": "",
    "患病多久": "",
    "用药情况": "",
    "过敏史": "",
    "既往病史": "",
}

=== 学习示例 (Few-shot Examples) ===
示例 1：
输入对话：
医生：你好，请问你孕后期下肢水肿吗？现在肿还是孕期肿？现在血压怎么样？下肢会不会有压痛？
病人：孕后期下肢有一点点不明显的水肿但起床后就消退了 ,现在是产后15-16天出现水肿，现在用手腕式量测的不知道准不准，血压是116/72,下肢有些地方按压会痛
医生：你现在还有用肝素吗
医生：结合你的情况，你是属于血液高凝人群，也称血栓前状态，高血压引起的水肿一般产后慢慢就消退了，很少会越来越重，你现在这种情况要小心1、下肢血栓形成，2、肾功能异常。可以回产后门诊复查，做个血压、尿常规、肾功能测试，还有双下肢血管彩超。最好还要排查一下心脏问题
病人：现在没用肝素了
医生：按我上面说的做，排查下肢静脉血栓
病人：好的,谢谢陈主任
病人：陈主任，我要过多八天才出月子，能不能出月再去检查，会不会太迟了
医生：不行，如果是下肢静脉血栓的话，是肯定不能拖的，血栓脱落是可能会导致肺栓塞的
病人：可以挂遗传或高危门诊的号吗？
医生：可以
病人：陈主任，如果检查是下肢静脉血栓，要怎么治疗
医生：用药，确定了再说吧，这个得在心血管内科治
病人：好的，谢谢陈主任

输出病历：
{
    "病情描述": "妊娠36周出现子痫前期，破水生产，妊娠期使用肝素（抗贝塔igm最高时16点多），抗核抗体阳性（吃甲泼尼龙片，硫酸羟氯喹转阴）",
    "希望获得的帮助": "什么原因引起的，怎么控制，要去医院做哪些检查",
    "怀孕情况": "未怀孕",
    "患病多久": "一周内",
    "用药情况": "蒙脱石散",
    "过敏史": "未提及",
    "既往病史": "未提及",
}
====================================
请注意：不要输出任何多余的解释性文字，只输出符合格式的 JSON 字符串。
"""

SYSTEM_MESSAGE_2 = """你是一个专业的体检内容安排AI助手。
你的任务是首先读取一份json格式的医生问诊笔记，格式如下：
{
    "病情描述": "",
    "希望获得的帮助": "",
    "怀孕情况": "",
    "患病多久": "",
    "用药情况": "",
    "过敏史": "",
    "既往病史": "",
}
然后你需要根据这八项的具体的患者指标，为患者生成一个有3-5项的体检方案，其中也可以包含对于患者的信息追问，要求输出json格式为：
{
    "1":"（示例）进行验血“，
    ”2“:"（示例）询问是否有过敏史或家族遗传病史",
    ...
}
请注意：不要输出任何多余的解释性文字，只输出符合格式的 JSON 字符串。
"""

SYSTEM_MESSAGE_NOT_USED = """你是一个专业的医疗信息补充AI助手。
你的任务是读取一份json格式的初步问诊笔记和一份json格式的患者在体检之后得到的补充数据信息，
随后利用后者来补充前者之中的信息并给出一份更全面的初步问诊笔记，以json格式输出，基础格式如下：
{
    "病情描述": "",
    "希望获得的帮助": "",
    "怀孕情况": "",
    "患病多久": "",
    "用药情况": "",
    "过敏史": "",
    "既往病史": "",
}
这只是基础的格式！你应当根据所得到的体检数据适当加入补充的条目并根据体检数据填入相应的内容。
请注意：不要输出任何多余的解释性文字，只输出符合格式的 JSON 字符串。
"""

SYSTEM_MESSAGE_3 = """你是一个专业的病状诊断AI助手。
你的任务是读取一份json格式的问诊笔记，和一份json格式的体检报告，
随后对患者的症状、疾病成因和严重程度等进行全面而准确的诊断，
并返回一份json格式的诊断书，格式如下：
{
    "病状诊断":"",
    "推测成因":"",
    "严重程度":"",
    ...
}
你可以根据实际情况适当增加条目，比如关于可能的诱发症的分析等等，但不要生成和治疗以及康复建议有关的内容。
请注意：不要输出任何多余的解释性文字，只输出符合格式的 JSON 字符串。
"""

SYSTEM_MESSAGE_4 = """你是一个专业的疾病治疗康复AI助手。
你的任务是读取一份json格式的患者诊断书，
随后给出一份方案来针对诊断书中的病症进行治疗，帮助患者康复，
需要返回一份json格式的康复方案，格式如下：
{
    "建议用药":"",
    "健康建议":"",
    ...
}
条目不限，内容不限，你应当根据具体的诊断内容进行合适的内容的填写。
请注意：不要输出任何多余的解释性文字，只输出符合格式的 JSON 字符串。
"""

SYSTEM_MESSAGE_TEST = """你是一个辅助生成一系列体检数据的AI测试助手。
你的任务是读取一份json格式的体检安排书和一份json格式的患者报告，
由于我们现在在进行一个医疗流程模拟，
我需要你根据患者报告，推测患者身体状况，自动生成合适的体检数据并填入一个基于体检安排书的json表中，
假设体检安排的格式为：
{
    "1":"进行验血“，
    ”2“:"询问是否有过敏史或家族遗传病史",
    ...
}
你应该返回：
{
    "验血结果":"...",
    "过敏史":"...",
    "家族遗传病史":"...",
    ...
}
按照体检安排中的条目严格填写，不要在json中填写多余的信息。
请注意：不要输出任何多余的解释性文字，只输出符合格式的 JSON 字符串。
"""

class LLMManager:
    def __init__(self):

        # For medical_record
        self.llm_1 = OpenAIChatCompletionClient(
            model="gpt-4.1",
            api_key=api_key,
            base_url="https://aihubmix.com/v1",
        )

        # For schedule
        self.llm_2 = OpenAIChatCompletionClient(
            model="gpt-4.1",
            api_key=api_key,
            base_url="https://aihubmix.com/v1",
        )

        # For diagnostic
        self.llm_3 = OpenAIChatCompletionClient(
            model="gpt-4.1",
            api_key=api_key,
            base_url="https://aihubmix.com/v1",
        )

        # For recovery_advice
        self.llm_4 = OpenAIChatCompletionClient(
            model="gpt-4.1",
            api_key=api_key,
            base_url="https://aihubmix.com/v1",
        )

        # For exam_result
        self.llm_test = OpenAIChatCompletionClient(
            model="gpt-4.1",
            api_key=api_key,
            base_url="https://aihubmix.com/v1",
        )

        self.agent_1 = AssistantAgent(
            name="Agent1",
            system_message=SYSTEM_MESSAGE_1,
            model_client=self.llm_1
        )

        self.agent_2 = AssistantAgent(
            name="Agent2",
            system_message=SYSTEM_MESSAGE_2,
            model_client=self.llm_2,
        )

        self.agent_3 = AssistantAgent(
            name="Agent3",
            system_message=SYSTEM_MESSAGE_3,
            model_client=self.llm_3
        )

        self.agent_4 = AssistantAgent(
            name="Agent4",
            system_message=SYSTEM_MESSAGE_4,
            model_client=self.llm_4
        )

        self.agent_test = AssistantAgent(
            name="AgentTest",
            system_message=SYSTEM_MESSAGE_TEST,
            model_client=self.llm_test
        )
    

