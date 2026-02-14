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