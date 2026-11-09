"""
【FE-AI Tutor】公式定義（official_def）品質精査・評価スクリプト
- 重点基準: 【評価1】シラバス整合性 × 【評価2】技術正確性
- タイムアウト15秒・5件バッチ保存で高速かつ安定動作
"""

import os
import sys
import time
from typing import Literal
import openpyxl
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
MASTER_FILE = "fe_study_master_23sheets.xlsx"
EVAL_FILE = "公式定義_品質精査評価シート.xlsx"
MODEL_NAME = "gemini-2.5-flash"

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

TARGET_SHEETS = [
    "3. コンピュータ構成要素", "5. ソフトウェア", "9. データベース",
    "10. ネットワーク", "11. セキュリティ", "12. システム開発技術", "22. 企業活動"
]

HEADERS = [
    "No", "用語名", "中分類", "公式定義テキスト（official_def）",
    "【評価1】シラバス整合性", "【評価2】技術正確性", "【評価3】初学者可読性",
    "総合合格判定(評価1&2)", "指摘事項・改善案コメント"
]

class OfficialDefEvaluation(BaseModel):
    eval1_syllabus: Literal["○", "△", "×"] = Field(description="IPAシラバスの出題基準・技術目的・役割に正確に合致しているか")
    eval2_accuracy: Literal["○", "△", "×"] = Field(description="技術的誤謬や類似用語との混同がなく、工学的に正確か（少しでも誤りがあれば×または△）")
    eval3_readability: Literal["○", "△", "×"] = Field(description="参考指標: 初学者にとって難解すぎないか")
    comment: str = Field(description="技術的整合性の観点からの批評（60〜100文字）")

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("🔑 Google Cloud Vertex AI に接続しました。")
except Exception as e:
    print(f"❌ API接続エラー: {e}")
    sys.exit(1)

if not os.path.exists(MASTER_FILE):
    print(f"❌ マスターExcelファイルが見つかりません: {MASTER_FILE}")
    sys.exit(1)

wb_eval = openpyxl.load_workbook(EVAL_FILE) if os.path.exists(EVAL_FILE) else openpyxl.Workbook()
excel_master = pd.ExcelFile(MASTER_FILE)
processed_count = 0

for sheetname in TARGET_SHEETS:
    matched = [s for s in excel_master.sheet_names if sheetname in s]
    if not matched:
        continue
    ms_name = matched[0]
    eval_title = f"{sheetname} 定義査読"

    df = pd.read_excel(MASTER_FILE, sheet_name=ms_name)
    def_col_name = "official_def" if "official_def" in df.columns else "kakomon_official_def"
    if def_col_name not in df.columns:
        continue

    valid_df = df[df[def_col_name].notna() & (df[def_col_name].astype(str).str.strip() != "")].copy()
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

    print(f"\n🧐 【{sheetname}】 公式定義 厳格査読（評価済: {len(existing)} / 全体: {len(all_rows)}）")

    for i, r_data in enumerate(all_rows, 1):
        term = str(r_data.get("term_name", "")).strip()
        if not term or term in ["None", "nan"] or term in existing:
            continue

        subcat = str(r_data.get("sub_category", sheetname)).strip()
        definition_text = str(r_data.get(def_col_name, "")).strip()

        print(f"  [{i}/{len(all_rows)}] 査読中: {term} ...", end="", flush=True)
        start_t = time.time()

        prompt = f"""あなたはIPA（情報処理推進機構）の基本情報技術者試験（科目A）シラバス策定委員および情報工学の技術査読員です。
提示された「用語の概要・公式定義」が、用語名に対して技術的・学術的に正確であるかを厳格に審査してください。

【対象用語】: {term}
【分野・中分類】: {subcat}
【公式定義テキスト】:
{definition_text}

■ 審査基準:
1. シラバス整合性: IPAシラバスの出題趣旨に合致し、用語の「目的・役割・技術的本質」が正しく捉えられているか（○/△/×）
2. 技術正確性: 工学的な誤り、ハルシネーション、他の類似概念との混同が一切ないか（○/△/×）
3. 初学者可読性（参考）: 2〜3文程度で定義として読める文章になっているか（○/△/×）
"""

        try:
            res = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OfficialDefResponse if False else OfficialDefEvaluation,
                    temperature=0.0
                )
            )
            ev: OfficialDefEvaluation = res.parsed
            if ev:
                # 評価1と評価2の両方が○であれば合格
                is_pass = "合格" if (ev.eval1_syllabus == "○" and ev.eval2_accuracy == "○") else "要改善"

                nr = ws.max_row + 1
                ws.cell(row=nr, column=1, value=nr - 1)
                ws.cell(row=nr, column=2, value=term)
                ws.cell(row=nr, column=3, value=subcat)
                ws.cell(row=nr, column=4, value=definition_text)
                ws.cell(row=nr, column=5, value=ev.eval1_syllabus)
                ws.cell(row=nr, column=6, value=ev.eval2_accuracy)
                ws.cell(row=nr, column=7, value=ev.eval3_readability)
                ws.cell(row=nr, column=8, value=is_pass)
                ws.cell(row=nr, column=9, value=ev.comment)

                existing.add(term)
                processed_count += 1
                elapsed = time.time() - start_t
                print(f" ✅ [{is_pass}] ({ev.eval1_syllabus}/{ev.eval2_accuracy}/{ev.eval3_readability}) [{elapsed:.1f}s]")

                if processed_count % 5 == 0:
                    wb_eval.save(EVAL_FILE)
            else:
                print(" ⚠️ パース失敗")

        except Exception as e:
            print(f" ❌ エラー: {e}")

        time.sleep(0.2)

    wb_eval.save(EVAL_FILE)

wb_eval.save(EVAL_FILE)
print("\n" + "=" * 60)
print(f"🎉 査読完了！ 結果を '{EVAL_FILE}' に保存しました。")
print("=" * 60)
