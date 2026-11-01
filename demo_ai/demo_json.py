import json
from random import choices
from sys import exception
from warnings import catch_warnings

from dotenv import load_dotenv
import os
import urllib.error
import urllib.request

load_dotenv()

SYSTEM_PROMPT = """
你是一个专业、耐心的中文 AI 助手。
请用清楚、自然的中文回答用户问题。
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




def chat_json(question:str) -> str:
    # 请求数据
    payload = {
        "model":MODEL,
        "messages":[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": question
            }
        ]
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
            answer = chat_json(question)
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