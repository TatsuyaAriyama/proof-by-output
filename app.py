import os
import re
import json
import sys
import locale
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# =========================
# UTF-8対策（日本語入力・出力）
# =========================
try:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    locale.setlocale(locale.LC_ALL, "")
except Exception:
    pass
# =========================
# Config
# =========================
APP_NAME = "Proof by Output"
MIN_CHARS = 60

TAGS = [
    {"name": "論点", "description": "何について話しているかが曖昧"},
    {"name": "根拠", "description": "なぜそう言えるかの理由が不足"},
    {"name": "具体", "description": "具体例やケースが不足"},
    {"name": "手順", "description": "説明の順序や進め方が不明瞭"},
    {"name": "留意", "description": "注意点・制約・例外条件が不足"},
    {"name": "用語", "description": "専門用語の説明が不足"},
]

TAG_TEXT = "\n".join([f"- {t['name']}：{t['description']}" for t in TAGS])

SYSTEM_PROMPT = f"""
あなたは学習内容の説明文を診断するコーチです。
ユーザーの説明文を評価し、つまずきタグを返します。

# つまずきタグ定義
{TAG_TEXT}

# 出力ルール
- 必ず日本語
- 必ずJSONのみ（前置き・補足文は禁止）
- tags は上記6タグから最大3つ選ぶ
- score は 0〜100 の整数
- improve_tips は短く具体的に3件以内
- improved_explanation は200〜320文字
- explanation_30sec は80〜140文字

# JSONスキーマ
{{
  "score": 0,
  "strengths": ["..."],
  "tags": [
    {{
      "name": "論点",
      "description": "何について話しているかが曖昧",
      "advice": "改善方法を1文"
    }}
  ],
  "improve_tips": ["..."],
  "improved_explanation": "...",
  "explanation_30sec": "..."
}}
"""
# =========================
# Setup
# =========================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY が見つかりません。.env を確認してください。")

client = OpenAI(api_key=api_key)
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def count_chars(text: str) -> int:
    # 改行や空白込みでカウント
    return len(text)


def safe_filename(text: str, max_len: int = 40) -> str:
    """
    保存ファイル名を安全なASCIIへ寄せる
    例:
      "githubについて" -> "github"
      "TypeScript Union型" -> "typescript_union"
      （英数が無ければ topic）
    """
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = text.strip("_")
    return (text[:max_len] or "topic")


def input_multiline(prompt: str) -> str:
    print(prompt)
    print("入力後、空行で終了（Enterを2回）")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def validate_input(topic: str, explanation: str) -> tuple[bool, str]:
    if not topic:
        return False, "トピック名は必須です。例: TypeScriptのUnion型"

    char_count = count_chars(explanation)
    if char_count < MIN_CHARS:
        remain = MIN_CHARS - char_count
        return (
            False,
            f"説明文は{MIN_CHARS}文字以上必要です（現在{char_count}文字、あと{remain}文字）。\n"
            "ヒント: 『〜とは』『なぜ使うか』『具体例』の3点を書くと到達しやすいです。"
        )

    return True, ""
    if not topic:
        return False, "トピック名は必須です。"
    char_count = count_chars(explanation)
    if char_count < MIN_CHARS:
        remain = MIN_CHARS - char_count
        return False, f"説明文は{MIN_CHARS}文字以上必要です（現在{char_count}文字、あと{remain}文字）。"
    return True, ""


def evaluate(topic: str, explanation: str) -> dict:
    user_prompt = f"""
    [トピック]
{topic}

[説明文]
{explanation}
"""
    res = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    content = res.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI応答がJSON形式ではありません: {e}\n---\n{content}")

    return data


def print_result(result: dict) -> None:
    print("\n==============================")
    print(f"{APP_NAME} - 診断結果")
    print("==============================")
    print(f"スコア: {result.get('score', 'N/A')} / 100")

    strengths = result.get("strengths", [])
    if strengths:
        print("\n良い点:")
        for s in strengths:
            print(f"- {s}")

    tags = result.get("tags", [])
    if tags:
        print("\n検知タグ:")
        for t in tags:
            name = t.get("name", "")
            desc = t.get("description", "")
            advice = t.get("advice", "")
            print(f"- {name}：{desc}")
            if advice:
                print(f"  改善: {advice}")

    tips = result.get("improve_tips", [])
    if tips:
        print("\n改善提案:")
        for tip in tips:
            print(f"- {tip}")

    print("\n改善版説明:")
    print(result.get("improved_explanation", ""))

    print("\n30秒説明:")
    print(result.get("explanation_30sec", ""))


def save_record(topic: str, explanation: str, result: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = safe_filename(topic)
    path = OUTPUT_DIR / f"{ts}_{name}.json"

    payload = {
        "app": APP_NAME,
        "created_at": datetime.now().isoformat(),
        "topic": topic,
        "explanation": explanation,
        "char_count": count_chars(explanation),
        "result": result,
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return path


def main() -> None:
    print(f"=== {APP_NAME} ===")
    print("理解は、アウトプットで証明する。")
    print(f"説明文は{MIN_CHARS}文字以上で入力してください。\n")

    topic = input("トピック名: ").strip()
    explanation = input_multiline("\n説明文を入力してください。")

    ok, msg = validate_input(topic, explanation)
    if not ok:
        print(f"\n入力エラー: {msg}")
        return

    try:
        result = evaluate(topic, explanation)
        print_result(result)
        save_path = save_record(topic, explanation, result)
        print(f"\n保存先: {save_path}")
    except Exception as e:
        print(f"\n実行エラー: {e}")


if __name__ == "__main__":
    main()