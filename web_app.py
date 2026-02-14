import os
import json
import re
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

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
- improve_tips は少なくとも1件、最大3件
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
client = OpenAI(api_key=api_key) if api_key else None

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def count_chars(text: str) -> int:
    return len(text)


def safe_filename(text: str, max_len: int = 40) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = text.strip("_")
    return (text[:max_len] or "topic")


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

    if not api_key:
        return False, "OPENAI_API_KEY が見つかりません。.env を確認してください。"

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
    return json.loads(content)


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


def load_history(limit: int = 30) -> list[dict]:
    files = sorted(OUTPUT_DIR.glob("*.json"), reverse=True)[:limit]
    records = []
    for p in files:
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data["_file"] = str(p)
            records.append(data)
        except Exception:
            continue
    return records


def render_diagnosis_result(result: dict):
    st.subheader("診断結果")
    st.metric("スコア", f"{result.get('score', 'N/A')} / 100")

    strengths = result.get("strengths", [])
    if strengths:
        st.markdown("### 良い点")
        for s in strengths:
            st.markdown(f"- {s}")

    tags = result.get("tags", [])
    if tags:
        st.markdown("### 検知タグ")
        for t in tags:
            st.markdown(f"- **{t.get('name','')}**：{t.get('description','')}")
            if t.get("advice"):
                st.markdown(f"  - 改善: {t.get('advice')}")

    tips = result.get("improve_tips", [])
    if tips:
        st.markdown("### 改善提案")
        for tip in tips:
            st.markdown(f"- {tip}")

    st.markdown("### 改善版説明")
    st.write(result.get("improved_explanation", ""))

    st.markdown("### 30秒説明")
    st.write(result.get("explanation_30sec", ""))


# =========================
# UI
# =========================
st.set_page_config(page_title=APP_NAME, page_icon="🧠", layout="centered")
st.title(APP_NAME)
st.caption("理解は、アウトプットで証明する。")

mode = st.sidebar.radio("メニュー", ["診断", "履歴"], index=0)

if mode == "診断":
    topic = st.text_input("トピック名", placeholder="例: TypeScriptのUnion型")
    explanation = st.text_area(
        "説明文（60文字以上）",
        placeholder="ここに自分の説明を書いてください。",
        height=220,
    )

    chars = count_chars(explanation)
    st.write(f"文字数: **{chars}** / 最低 **{MIN_CHARS}**")

    if st.button("診断する", type="primary"):
        ok, msg = validate_input(topic, explanation)
        if not ok:
            st.warning(msg)
        else:
            try:
                with st.spinner("診断中..."):
                    result = evaluate(topic, explanation)

                render_diagnosis_result(result)
                save_path = save_record(topic, explanation, result)
                st.success(f"結果を保存しました: {save_path}")

            except json.JSONDecodeError:
                st.error("AI応答の解析に失敗しました。もう一度実行してください。")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

else:
    st.subheader("診断履歴")
    records = load_history(limit=50)

    if not records:
        st.info("まだ履歴がありません。診断を実行するとここに表示されます。")
    else:
        for i, rec in enumerate(records, start=1):
            topic = rec.get("topic", "(no topic)")
            created = rec.get("created_at", "")
            score = rec.get("result", {}).get("score", "N/A")
            char_count = rec.get("char_count", 0)

            with st.expander(f"{i}. {topic} | score: {score} | {created}"):
                st.write(f"文字数: {char_count}")
                st.write(f"ファイル: {rec.get('_file', '')}")

                st.markdown("**入力説明文**")
                st.write(rec.get("explanation", ""))

                st.markdown("**診断結果**")
                render_diagnosis_result(rec.get("result", {}))