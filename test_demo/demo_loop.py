import json
import os
import urllib.error
import urllib.request
from dotenv import load_dotenv


load_dotenv()

BASE_URL = os.getenv("BASE_URL") or ""
if not BASE_URL:
    raise RuntimeError("没有 BASE_URL，无法请求真实模型。请先在 .env 里配置 BASE_URL。")

MODEL = os.getenv("MODEL") or ""
if not MODEL:
    raise RuntimeError("没有 MODEL，无法请求真实模型。请先在 .env 里配置 MODEL。")

API_KEY = os.getenv("API_KEY") or ""
if not API_KEY:
    raise RuntimeError("没有 API Key，无法请求真实模型。请先在 .env 里配置 API_KEY。")


SYSTEM_PROMPT = """
你是一个耐心、直接、靠谱的中文 AI 助手。
请优先用清晰的中文回答用户问题。
如果问题信息不足，可以先说明需要补充什么。
"""


def ask_model(question: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "thinking": {"type": "disabled"},
        "max_tokens": 1000,
    }

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
    except urllib.error.URLError as exc:
        raise RuntimeError(f"连接模型接口失败：{exc.reason}") from exc

    content = response_data["choices"][0]["message"]["content"]
    if not content:
        raise RuntimeError("模型返回了空 content，请重试或检查 prompt。")

    return content.strip()


def main() -> None:
    print("输入 exit、quit 或 退出 可以结束程序。")

    while True:
        try:
            question = input("\n输入你的问题：").strip().lstrip("\ufeff")
        except EOFError:
            print("\n已结束问答循环。")
            break

        command = question.lower()
        if command in {"exit", "quit"} or question == "退出":
            print("已结束问答循环。")
            break

        if not question:
            print("问题不能为空，请重新输入。")
            continue

        try:
            answer = ask_model(question)
        except RuntimeError as exc:
            print(f"调用失败：{exc}")
            continue

        print(f"\n大模型的回答：{answer}")


if __name__ == "__main__":
    main()
