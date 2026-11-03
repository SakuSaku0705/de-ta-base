"""
【FE-AI Tutor】試験直結解説（exam_point_text）品質精査・評価スクリプト
- 3軸厳格評価: 正解キーワード妥当性 / 動作ロジック理解度 / 技術正確性
- 判定結果を '試験直結解説_品質精査評価シート.xlsx' へ出力
"""

import os
import sys
import time
from typing import Literal
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
MASTER_FILE = "fe_study_master_23sheets.xlsx"
EVAL_FILE = "試験直結解説_品質精査評価シート.xlsx"

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

TARGET_SHEETS = [
    "3. コンピュータ構成要素", "5. ソフトウェア", "9. データベース",
    "10. ネットワーク", "11. セキュリティ", "12. システム開発技術", "22. 企業活動"
]

HEADERS = [
    "No", "用語名", "中分類", "試験直結解説（exam_point_text）",
    "【評価1】正解キーワード妥当性", "【評価2】動作ロジック理解度", "【評価3】技術正確性",
    "指摘事項・改善案コメント"
]

class StrictExamPointEvaluation(BaseModel):
    eval1_keywords: Literal["○", "△", "×"] = Field(description="正解を見抜くキーワードや頻出言い換えの妥当性")
    eval2_logic: Literal["○", "△", "×"] = Field(description="仕組みやアルゴリズム動作の分かりやすさ")
    eval3_accuracy: Literal["○", "△", "×"] = Field(description="技術的誤謬やハルシネーションがないか")
    comment: str = Field(description="初学者が過去問で点数を取るための改善アドバイス（60〜100文字）")

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"❌ API接続エラー: {e}")
    sys.exit(1)

wb_eval = openpyxl.load_workbook(EVAL_FILE) if os.path.exists(EVAL_FILE) else openpyxl.Workbook()
excel_master = pd.ExcelFile(MASTER_FILE)

for sheetname in TARGET_SHEETS:
    matched = [s for s in excel_master.sheet_names if sheetname in s]
    if not matched:
        continue
    ms_name = matched[0]
    eval_title = f"{sheetname} 査読"

    df = pd.read_excel(MASTER_FILE, sheet_name=ms_name)
    if "exam_point_text" not in df.columns:
        continue

    valid_df = df[df["exam_point_text"].notna() & (df["exam_point_text"].astype(str).str.strip() != "")].copy()
    all_rows = valid_df.to_dict("records")

    if eval_title in wb_eval.sheetnames:
        ws = wb_eval[eval_title]
    else:
        ws = wb_eval.create_sheet(title=eval_title)
        for c_idx, h in enumerate(HEADERS, 1):
            ws.cell(row=1, column=c_idx, value=h)

    existing = set()
    for r in range(2, ws.max_row + 1):
        t_val = ws.cell(row=r, column=2).value
        e1_val = ws.cell(row=r, column=5).value
        if t_val and e1_val:
            existing.add(str(t_val).strip())

    print(f"\n🧐 【{sheetname}】 査読開始（登録済: {len(existing)} / 全体: {len(all_rows)}）")

    for i, r_data in enumerate(all_rows, 1):
        term = str(r_data.get("term_name", "")).strip()
        if not term or term in existing:
            continue

        subcat = str(r_data.get("sub_category", sheetname)).strip()
        exam_text = str(r_data.get("exam_point_text", "")).strip()

        print(f"[{i}/{len(all_rows)}] 査読中: {term} ...", end="", flush=True)

        prompt = f"""あなたは国家試験「基本情報技術者試験（科目A）」の厳格な指導員・技術査読者です。
初学者が過去問の正解・不正解を見抜くために作成された解説文（exam_point_text）を、厳格に3軸で審査してください。

【対象用語】: {term}
【分野】: {subcat}
【生成テキスト】:
{exam_text}

■ 審査基準（甘い評価は禁止。粗探しを行い批判的に判定すること）：
1. 正解キーワード妥当性: 過去問で頻出する選択肢の言い換え・判定ポイントを突いているか（○/△/×）
2. 動作ロジック理解度: 単なる比喩に逃げず、仕組みや処理の流れを初学者向けに説明できているか（○/△/×）
3. 技術正確性: 誤謬や用語の取り違えがないか（○/△/×）
"""
        time.sleep(0.3)
        try:
            res = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=StrictExamPointEvaluation, temperature=0.1)
            )
            ev: StrictExamPointEvaluation = res.parsed
            nr = ws.max_row + 1
            ws.cell(row=nr, column=1, value=nr - 1)
            ws.cell(row=nr, column=2, value=term)
            ws.cell(row=nr, column=3, value=subcat)
            ws.cell(row=nr, column=4, value=exam_text)
            ws.cell(row=nr, column=5, value=ev.eval1_keywords)
            ws.cell(row=nr, column=6, value=ev.eval2_logic)
            ws.cell(row=nr, column=7, value=ev.eval3_accuracy)
            ws.cell(row=nr, column=8, value=ev.comment)
            wb_eval.save(EVAL_FILE)
            existing.add(term)
            print(f" ✅ ({ev.eval1_keywords}/{ev.eval2_logic}/{ev.eval3_accuracy})")
        except Exception as e:
            print(f" ⚠️ エラー: {e}")

wb_eval.save(EVAL_FILE)
print(f"\n🎉 査読結果を '{EVAL_FILE}' に保存しました。")
