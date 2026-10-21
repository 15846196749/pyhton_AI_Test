import json
import os
import urllib.error
import urllib.request
from dotenv import load_dotenv  # 从 python-dotenv 库中导入 load_dotenv


load_dotenv() # 加载 .env 文件中的环境变量
# 1. 模型连接配置
BASE_URL = os.getenv("BASE_URL") or ""
if not BASE_URL:
    raise RuntimeError("没有 BASE_URL，无法请求真实模型。请先去 DeepSeek Platform 查看 API Endpoint。")
MODEL = os.getenv("MODEL") or ""
if not MODEL:
    raise RuntimeError("没有 MODEL，无法请求真实模型。请先去 DeepSeek Platform 查看可用模型列表。")

# 3. API Key
API_KEY = os.getenv("API_KEY") or ""
if not API_KEY:
    raise RuntimeError("没有 API Key，无法请求真实模型。请先去 DeepSeek Platform 创建 API Key。")

SYSTEM_PROMPT = """
你是一个专业、耐心的中文 AI 助手。
请用清楚、自然的中文回答用户问题。
"""

USER_QUESTION = "请你帮我判断一下：这个瓜深绿色条纹，底部发黄，拍起来声音沉闷，重 5.2 公斤，老板说今天早上刚进货、包熟。这个瓜能买吗？"

#输入：系统提示词 system_prompt + 用户问题 user_question
#        ↓
#调用：模型服务接口
#        ↓
#请求：大模型 API 接口
#        ↓
#读取：模型返回的原始内容
#        ↓
#输出：模型返回的文本回答

def chat_json_example() -> str:
    # 3. 组装 OpenAI-compatible Chat Completions 请求体
    payload = {
        "model": MODEL,
        "messages": [
            # system 消息：告诉模型当前要扮演什么角色
            {"role": "system", "content": SYSTEM_PROMPT},
            # user 消息：把用户问题直接发给模型
            {"role": "user", "content": USER_QUESTION},
        ],
        # 教学示例里不需要思考模式，先关掉，方便看到一段直接回答。
        "thinking": {"type": "disabled"},
        "max_tokens": 800,
    }

    # 4. 请求真实模型接口
    request = urllib.request.Request(
        url=f"{BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"模型接口请求失败：HTTP {exc.code}\n{error_body}") from exc

    # 5. 从 Chat Completions 返回结构里取出模型内容
    content = response_data["choices"][0]["message"]["content"]
    if not content:
        raise RuntimeError("模型返回了空 content，请重试或检查 prompt。")

    # 6. 第一章先不做结构化解析，直接返回模型生成的文本
    return content.strip()


def main() -> None:
    answer = chat_json_example()
    print(answer)


if __name__ == "__main__":
    main()
