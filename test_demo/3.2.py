import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def clean_text(value: str) -> str:
    return value.encode("utf-8", errors="replace").decode("utf-8")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(Path(__file__).with_name(".env"))

BASE_URL = os.getenv("BASE_URL") or ""
MODEL = os.getenv("MODEL") or ""
API_KEY = os.getenv("API_KEY") or ""

MEMORY_LIMIT = 10
CATEGORIES = {"质量问题", "物流问题", "退款售后", "使用咨询", "其他"}
PRIORITIES = {"高", "中", "低"}
EMOTIONS = {"平静", "着急", "生气", "无法判断"}
UNSUPPORTED_POLICY_CLAIMS = {
    "三包",
    "30天",
    "30 天",
    "十五天",
    "15天",
    "15 天",
    "必定退款",
    "一定退款",
    "支持退货",
    "可以退货",
    "可退货",
    "处理退货",
    "退货或换货",
    "安排退换货",
}

SYSTEM_PROMPT = """
你是一个 AI 售后客服助手，负责根据用户问题生成客服回复。

你的目标：
1. 先判断用户问题类型、优先级和情绪。
2. 再给出一段可以给客服参考的回复。
3. 如果信息不足，先提出需要补充的问题，不要编造订单号、金额、物流状态或售后政策。

请严格返回一个合法 JSON 对象，不要返回 Markdown，不要使用代码块。

JSON 字段要求：
- category：只能是「质量问题」「物流问题」「退款售后」「使用咨询」「其他」
- priority：只能是「高」「中」「低」
- emotion：只能是「平静」「着急」「生气」「无法判断」
- needs_human：布尔值，表示是否建议转人工
- answer：给客服参考的回复草稿
- follow_up_question：还需要向用户追问什么；如果不需要，返回空字符串
- evidence：一句话说明判断依据

判断规则：
- 用户要求退款、投诉、表达强烈不满，priority 通常为「高」，needs_human 通常为 true。
- 涉及商品损坏、无法使用、漏水、没声音等情况，category 通常为「质量问题」。
- 涉及发货、快递、没收到、物流异常，category 通常为「物流问题」。
- 涉及怎么使用、怎么安装、怎么连接，category 通常为「使用咨询」。
- 如果用户只是问候、介绍姓名，或询问最近对话中已经提供的信息，也要正常回应，category 用「其他」，priority 用「低」。
- 遇到「刚才那个」「上面说的」「我叫什么」这类说法时，可以结合最近 10 轮对话理解，但不要使用没有出现过的信息。
- 不要引用用户没有提供的具体售后政策，比如「三包」「30 天内可退」或「一定退款」。
- 如果用户问超过 7 天还能不能退，只能说需要结合订单、商品状态和平台售后规则人工核实。
- 在没有订单和平台规则时，不要说「支持退货」「可以退货」或「安排退换货」。
- category 为「质量问题」或「退款售后」时，needs_human 必须是 true。
- priority 为「高」时，needs_human 必须是 true。
"""


def build_user_prompt(question: str, history: list[dict[str, Any]]) -> str:
    recent_history = history[-MEMORY_LIMIT:]
    if recent_history:
        history_payload = [
            {
                "轮次": turn["round"],
                "用户问题": turn["question"],
                "助手回复": turn["card"].get("answer", ""),
                "问题类型": turn["card"].get("category", ""),
            }
            for turn in recent_history
        ]
        history_text = json.dumps(
            history_payload,
            ensure_ascii=False,
            indent=2,
        )
    else:
        history_text = "无"

    return f"""
最近 10 轮对话（从旧到新）：
{history_text}

当前用户问题：
{question}

请结合最近 10 轮对话和当前问题，生成本轮售后客服结构化结果。
"""


def request_model(question: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    if not BASE_URL:
        raise RuntimeError("没有 BASE_URL，无法请求真实模型。请先在 .env 中配置模型 API Endpoint。")
    if not MODEL:
        raise RuntimeError("没有 MODEL，无法请求真实模型。请先在 .env 中配置模型名称。")
    if not API_KEY:
        raise RuntimeError("没有 API_KEY，无法请求真实模型。请先在 .env 中配置 API Key。")

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, history)},
        ],
        "response_format": {"type": "json_object"},
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

    content = response_data["choices"][0]["message"]["content"]
    if not content:
        raise RuntimeError("模型返回了空 content，请重试或检查 prompt。")

    result = json.loads(content)
    if not isinstance(result, dict):
        raise RuntimeError("模型返回的 JSON 不是对象。")
    return result


def validate_support_card(card: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_fields = [
        "category",
        "priority",
        "emotion",
        "needs_human",
        "answer",
        "follow_up_question",
        "evidence",
    ]

    for field in required_fields:
        if field not in card:
            errors.append(f"缺少字段：{field}")

    if card.get("category") not in CATEGORIES:
        errors.append("category 不在允许范围内")
    if card.get("priority") not in PRIORITIES:
        errors.append("priority 不在允许范围内")
    if card.get("emotion") not in EMOTIONS:
        errors.append("emotion 不在允许范围内")
    if not isinstance(card.get("needs_human"), bool):
        errors.append("needs_human 必须是布尔值")
    if card.get("category") in {"质量问题", "退款售后"} and card.get("needs_human") is not True:
        errors.append("质量问题或退款售后必须建议转人工")
    if card.get("priority") == "高" and card.get("needs_human") is not True:
        errors.append("priority 为高时 needs_human 必须为 true")
    if not isinstance(card.get("answer"), str) or not card.get("answer"):
        errors.append("answer 必须是非空字符串")
    if not isinstance(card.get("follow_up_question"), str):
        errors.append("follow_up_question 必须是字符串")
    if not isinstance(card.get("evidence"), str) or not card.get("evidence"):
        errors.append("evidence 必须是非空字符串")

    answer_and_evidence = f"{card.get('answer', '')}\n{card.get('evidence', '')}"
    if any(token in answer_and_evidence for token in UNSUPPORTED_POLICY_CLAIMS):
        errors.append("answer 或 evidence 包含输入中没有提供的具体售后政策")

    return errors


def extract_name_from_text(text: str) -> str:
    if any(token in text for token in ["什么", "啥", "谁"]):
        return ""

    patterns = [
        r"我叫\s*([^\s，。,！!？?]+)",
        r"我是\s*([^\s，。,！!？?]+)",
        r"我的名字是\s*([^\s，。,！!？?]+)",
        r"名字叫\s*([^\s，。,！!？?]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def extract_user_name(history: list[dict[str, Any]]) -> str:
    for turn in reversed(history[-MEMORY_LIMIT:]):
        question = str(turn.get("question", ""))
        name = extract_name_from_text(question)
        if name:
            return name
    return ""


def fallback_support_card(
    question: str,
    history: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    previous_category = ""
    if history:
        previous_category = str(history[-1]["card"].get("category", ""))

    current_name = extract_name_from_text(question)
    if current_name:
        return {
            "category": "其他",
            "priority": "低",
            "emotion": "平静",
            "needs_human": False,
            "answer": f"你好，{current_name}。有什么售后问题可以直接告诉我。",
            "follow_up_question": "",
            "evidence": "用户提供了自己的称呼，暂未提出具体售后问题。",
        }

    if question.lower() in {"hi", "hello"} or question in {"你好", "您好"}:
        return {
            "category": "其他",
            "priority": "低",
            "emotion": "平静",
            "needs_human": False,
            "answer": "您好，请问有什么售后问题需要我帮您处理？",
            "follow_up_question": "",
            "evidence": "用户只是打招呼，未提出具体售后问题。",
        }

    if any(token in question for token in ["我叫什么", "我叫啥", "我的名字", "我是谁"]):
        name = extract_user_name(history)
        if name:
            return {
                "category": "其他",
                "priority": "低",
                "emotion": "平静",
                "needs_human": False,
                "answer": f"你前面说过你叫{name}。",
                "follow_up_question": "",
                "evidence": "根据最近 10 轮对话中用户的自我介绍回答。",
            }

    if any(token in question for token in ["没声音", "坏", "漏水", "破损", "无法使用", "故障"]):
        category = "质量问题"
    elif any(token in question for token in ["退款", "退货", "七天", "7天", "7 天", "超过7天", "超过 7 天", "售后"]):
        category = "退款售后"
    elif any(token in question for token in ["物流", "快递", "发货", "没收到"]):
        category = "物流问题"
    elif any(token in question for token in ["怎么用", "使用", "安装", "连接", "设置"]):
        category = "使用咨询"
    elif previous_category and any(token in question for token in ["刚才", "上面", "那个", "这个"]):
        category = previous_category
    else:
        category = "其他"

    emotion = "平静"
    if any(token in question for token in ["生气", "投诉", "太差", "没人管"]):
        emotion = "生气"
    elif any(token in question for token in ["急", "马上", "赶紧", "尽快"]):
        emotion = "着急"

    priority = "中"
    needs_human = category in {"质量问题", "退款售后"} or emotion in {"着急", "生气"}
    if needs_human:
        priority = "高"
    elif category == "使用咨询":
        priority = "低"

    if category == "质量问题":
        follow_up_question = "请补充订单号、购买时间，以及能说明问题的照片或视频。"
        answer = "您好，很抱歉给您带来不好的体验。我们先帮您核实商品情况，请您提供订单号、购买时间，以及问题照片或视频。核实后会根据售后规则协助处理。"
    elif category == "退款售后":
        follow_up_question = "请补充订单号、购买时间、商品状态，以及是否已经申请过售后。"
        answer = "您好，我理解您想确认退款或退货处理。请您先提供订单号、购买时间和商品当前状态，我们会根据售后规则核实可选方案，不会在信息不足时直接承诺结果。"
    elif category == "物流问题":
        follow_up_question = "请补充订单号或物流单号，方便查询最新状态。"
        answer = "您好，我们可以先帮您核实物流状态。请您提供订单号或物流单号，我会根据查询结果给出下一步处理建议。"
    elif category == "使用咨询":
        follow_up_question = "请补充商品型号和当前操作步骤。"
        answer = "您好，我可以帮您一起排查使用问题。请您补充商品型号和目前卡在哪一步，我会按步骤给您说明。"
    else:
        follow_up_question = "请补充订单号、商品名称和具体诉求。"
        answer = "您好，我们已经收到您的问题。为了更准确地处理，请您补充订单号、商品名称和具体诉求，我们会继续协助核实。"

    if history and any(token in question for token in ["刚才", "上面", "那个", "这个"]):
        answer = f"我理解您说的是上一轮提到的「{previous_category}」。{answer}"

    return {
        "category": category,
        "priority": priority,
        "emotion": emotion,
        "needs_human": needs_human,
        "answer": answer,
        "follow_up_question": follow_up_question,
        "evidence": f"根据当前问题关键词和最近 10 轮上下文做保守判断；fallback 原因：{reason}",
    }


def ask_model(
    question: str,
    history: list[dict[str, Any]],
    *,
    use_model: bool = True,
) -> tuple[str, dict[str, Any], list[str]]:
    if use_model:
        try:
            card = request_model(question, history)
            errors = validate_support_card(card)
            if not errors:
                return "model", card, errors
            reason = "模型输出未通过校验：" + "；".join(errors)
        except Exception as exc:
            reason = str(exc)
    else:
        reason = "演示模式手动关闭真实模型请求"

    card = fallback_support_card(question, history, reason)
    errors = validate_support_card(card)
    return "fallback", card, errors


def print_turn(index: int, question: str, source: str, card: dict[str, Any], errors: list[str]) -> None:
    print(f"\n=== 第 {index} 轮：{question} ===")
    print(f"来源：{source}")
    print(json.dumps(card, ensure_ascii=False, indent=2))

    if errors:
        print("Schema 校验失败：")
        for error in errors:
            print(f"- {error}")
    else:
        print("Schema 校验通过。")


def run_demo(use_model: bool) -> None:
    questions = [
        "你好",
        "我叫小马",
        "我叫什么？",
        "我买的蓝牙耳机左耳没声音，想退货。",
        "我叫什么？",
    ]
    history: list[dict[str, Any]] = []

    for index, question in enumerate(questions, start=1):
        source, card, errors = ask_model(question, history, use_model=use_model)
        print_turn(index, question, source, card, errors)
        history.append({"round": index, "question": question, "card": card})
        del history[:-MEMORY_LIMIT]


def run_interactive(use_model: bool) -> None:
    history: list[dict[str, Any]] = []
    print("输入 exit、quit 或 退出 可以结束程序。")

    index = 1
    while True:
        try:
            question = clean_text(input("\n用户问题：")).strip().lstrip("\ufeff")
        except EOFError:
            print("\n已结束售后问答。")
            break

        command = question.lower()
        if command in {"exit", "quit"} or question == "退出":
            print("已结束售后问答。")
            break

        if not question:
            print("问题不能为空，请重新输入。")
            continue

        source, card, errors = ask_model(question, history, use_model=use_model)
        print_turn(index, question, source, card, errors)
        history.append({"round": index, "question": question, "card": card})
        del history[:-MEMORY_LIMIT]
        index += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="售后客服 Prompt 问答系统")
    parser.add_argument("--demo", action="store_true", help="运行两轮内置演示，不进入交互输入")
    parser.add_argument("--no-model", action="store_true", help="不请求真实模型，只运行 fallback 链路")
    args = parser.parse_args()

    use_model = not args.no_model
    if args.demo:
        run_demo(use_model)
    else:
        run_interactive(use_model)


if __name__ == "__main__":
    main()
