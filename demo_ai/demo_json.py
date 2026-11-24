import json
from random import choices
from sys import exception
from typing import Any
from warnings import catch_warnings

from dotenv import load_dotenv
import os
import urllib.error
import urllib.request

load_dotenv()

SYSTEM_PROMPT = """
你是一个资深的 AI 售后客服助手，负责根据用户问题生成客服回复草稿及结构化标签。

你的目标：
1. 准确判断用户问题的类型、优先级和用户情绪。
2. 给出一段可以直接给客服参考的回复草稿（answer）。
3. 如果信息不足，不要编造订单号、金额、物流状态或售后政策，而是通过 follow_up_question 追问。
4. 严格返回一个合法的纯 JSON 对象，绝对不要包含 Markdown 标记（如 ```json ），不要输出任何 JSON 以外的解释性文字。

JSON 字段要求：
- category: 字符串，只能是「质量问题」「物流问题」「退款售后」「使用咨询」「其他」之一。
- priority: 字符串，只能是「高」「中」「低」之一。
- emotion: 字符串，只能是「平静」「着急」「生气」「无法判断」之一。
- needs_human: 布尔值，表示是否建议转人工。
- answer: 字符串，给客服参考的回复草稿。如果信息严重不足，可在此处写“请提供...”。
- follow_up_question: 字符串，需要向用户追问的问题；如果不需要追问，返回空字符串 ""。
- evidence: 字符串，用一句话简述你的判断依据。

【判断规则】：
1. 优先级与转人工：
   - 只要用户要求退款、投诉、表达强烈不满，priority 为「高」，needs_human 必须为 true。
   - 只要 category 为「质量问题」或「退款售后」，needs_human 必须为 true。
   - 如果 category 为「其他」且仅是问候/查信息，priority 默认「低」，needs_human 为 false。
2. 分类定义（若有重叠，以根本诉求或根本原因为准）：
   - 质量问题：涉及商品损坏、无法使用、漏水、没声音等故障。
   - 物流问题：涉及发货、快递、没收到、物流异常。
   - 退款售后：涉及退换货流程、退款进度、运费险等（非质量原因的退款）。
   - 使用咨询：涉及怎么使用、怎么安装、怎么连接。
3. 上下文理解：
   - 遇到「刚才那个」「上面说的」「我叫什么」等指代词时，结合最近 10 轮对话理解，但不要捏造对话中没有出现过的信息。
4. 客服话术限制（严禁过度承诺）：
   - 不要引用用户没有提供的具体售后政策（如「三包」「30天可退」「一定退款」）。
   - 如果用户问超过 7 天还能不能退，answer 只能回复：需要结合订单、商品状态和平台售后规则人工核实。
   - 在没有订单和平台规则时，不要说「支持退货」「可以退货」或「安排退换货」。
"""

USER_QUESTION = "请你帮我判断一下：这个瓜深绿色条纹，底部发黄，拍起来声音沉闷，重 5.2 公斤，老板说今天早上刚进货、包熟。这个瓜能买吗？"


MODEL = os.getenv("MODEL")
if not MODEL:
    raise RuntimeError("没有配置模型")
BASE_URL = os.getenv("BASE_URL")
if not BASE_URL:
    raise RuntimeError("不存在模型调用地址")
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY为空")

# 历史问答记录
history_list:list[dict[str,Any]] = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT
    }
]


def chat_json(question:str,history_list:list[dict[str,Any]]) -> str:

    # 新问题加入到messages中
    question_dict = {
        "role": "user",
        "content": question
    }
    history_list.append(question_dict)

    all_talk = json.dumps(history_list,ensure_ascii=False)
    print("历史对话 history_list: "+all_talk)

    # 请求数据
    payload = {
        "model":MODEL,
        "messages":history_list
    }
    # 构建请求
    request = urllib.request.Request(
        url = f"{BASE_URL.rstrip("/")}/chat/completions",
        data= json.dumps(payload,ensure_ascii=False).encode("UTF-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST"
        )
    
    #发送请求
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("UTF-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("UTF-8")
        raise RuntimeError(f"模型接口请求失败，返回{exc.code}\n{error_body}") 
    
    #获取模型返回的内容
    message = response_data["choices"][0]["message"]["content"]
    if not message:
        raise RuntimeError(f"模型返回内容为空")
    # 校验返回格式
    message_dict = json.load(message)
    
    # 记忆中加入回答
    model_answer = message_dict["answer"]+","+message_dict["follow_up_question"]
    # assistant 模型回答
    answer_dict = {
        "role": "assistant",
        "content": model_answer
    }
    history_list.append(answer_dict)
    # 兜底处理
    
    return message


# 问答loop
def chat_input()->None:
    while True:
        print("输入exit退出问答")
        question = input("\n输入问题:").strip()
        if not question:
            raise RuntimeError("问题为空")
        command = question.lower()
        if command.__eq__("exit"):
            print("退出问答")
            break
        try:
            answer = chat_json(question,history_list)
            print(f"模型回答:{answer}\n")
        except RuntimeError as exc:
            print(f"调用失败{exc}\n")
            continue






def main() -> None:
    # 写死问题
    # answer = chat_json()
    # print(answer)
    
    #输入问题
    chat_input()

if __name__ == "__main__":
    main()