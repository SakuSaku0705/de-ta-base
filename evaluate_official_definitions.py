"""
【FE-AI Tutor】用語概要・公式定義（official_def）品質精査・評価スクリプト
- 3軸厳格評価:
    1. シラバス整合性（用語の本質的役割・概念が過不足なく捉えられているか）
    2. 技術正確性（技術的な誤謬や類似概念との取り違え・ハルシネーションがないか）
    3. 初学者可読性（難解すぎず、2〜3文・100〜150文字程度で簡潔にまとまっているか）
- 判定結果を '公式定義_品質精査評価シート.xlsx' へ出力（自動再開対応）
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

# =========================================================
# 1. 認証 ＆ ファイル設定
# =========================================================
CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
MASTER_FILE = "fe_study_master_23sheets.xlsx"
EVAL_FILE = "公式定義_品質精査評価シート.xlsx"
MODEL_NAME = "gemini-2.5-flash"

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

TARGET_SHEETS = [
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動"
]

HEADERS = [
    "No", "用語名", "中分類", "公式定義テキスト（official_def）",
    "【評価1】シラバス整合性", "【評価2】技術正確性", "【評価3】初学者可読性",
    "指摘事項・改善案コメント"
]

# =========================================================
# 2. 厳格査読スキーマ定義
# =========================================================
class OfficialDefEvaluation(BaseModel):
    eval1_syllabus: Literal["○", "△", "×"] = Field(
        description="IPAシラバスの学習目標に合致し、用語の目的・役割が適切に捉えられているか"
    )
    eval2_accuracy: Literal["○", "△", "×"] = Field(
        description="技術的な誤謬、用語の取り違え、不正確な記述がないか（少しでも誤りがあれば×または△）"
    )
    eval3_readability: Literal["○", "△", "×"] = Field(
        description="初学者が理解しやすい平易な表現か。また2〜3文（100〜150文字程度）で簡潔か"
    )
    comment: str = Field(
        description="問題点や改善すべき表現についての客観的な指摘（問題なければ『シラバス定義として適切』と記入、60〜100文字）"
    )

# =========================================================
# 3. クライアント初期化
# =========================================================
try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("🔑 Google Cloud Vertex AI に接続しました。")
except Exception as e:
    print(f"❌ API接続エラー: {e}")
    sys.exit(1)

if not os.path.exists(MASTER_FILE):
    print(f"❌ マスターExcelファイルが見つかりません: {MASTER_FILE}")
    sys.exit(1)

# 評価シートの初期化または読み込み
wb_eval = openpyxl.load_workbook(EVAL_FILE) if os.path.exists(EVAL_FILE) else openpyxl.Workbook()
excel_master = pd.ExcelFile(MASTER_FILE)

# =========================================================
# 4. シートごとの査読処理
# =========================================================
for sheetname in TARGET_SHEETS:
    matched = [s for s in excel_master.sheet_names if sheetname in s]
    if not matched:
        continue
    ms_name = matched[0]
    eval_title = f"{sheetname} 定義査読"

    df = pd.read_excel(MASTER_FILE, sheet_name=ms_name)
    def_col_name = "official_def" if "official_def" in df.columns else "kakomon_official_def"
    if def_col_name not in df.columns:
        print(f"⚠️ '{ms_name}' に定義列が見つかりません。スキップします。")
        continue

    # 有効な定義が入っている行を抽出
    valid_df = df[df[def_col_name].notna() & (df[def_col_name].astype(str).str.strip() != "")].copy()
    all_rows = valid_df.to_dict("records")

    if eval_title in wb_eval.sheetnames:
        ws = wb_eval[eval_title]
    else:
        ws = wb_eval.create_sheet(title=eval_title)
        for c_idx, h in enumerate(HEADERS, 1):
            ws.cell(row=1, column=c_idx, value=h)

    # 既存の評価済み用語を収集（自動再開用）
    existing = set()
    for r in range(2, ws.max_row + 1):
        t_val = ws.cell(row=r, column=2).value
        e1_val = ws.cell(row=r, column=5).value
        if t_val and e1_val:
            existing.add(str(t_val).strip())

    print(f"\n🧐 【{sheetname}】 公式定義査読（評価済: {len(existing)} / 全体: {len(all_rows)}）")

    for i, r_data in enumerate(all_rows, 1):
        term = str(r_data.get("term_name", "")).strip()
        if not term or term in ["None", "nan"] or term in existing:
            continue

        subcat = str(r_data.get("sub_category", sheetname)).strip()
        definition_text = str(r_data.get(def_col_name, "")).strip()

        print(f"  [{i}/{len(all_rows)}] 査読中: {term} ...", end="", flush=True)

        prompt = f"""あなたはIPA（情報処理推進機構）の基本情報技術者試験（科目A）シラバス策定委員および情報科学教育の厳格な技術査読員です。
学習支援システムで初学者に提示する「用語の概要・公式定義」を、厳格に3軸で批判的に審査してください。
甘い評価（安易なオール○）は厳禁です。粗探しを行い、疑わしい点や不足点があれば躊躇なく「△」や「×」をつけてください。

【対象用語】: {term}
【分野・中分類】: {subcat}
【生成された公式定義テキスト】:
{definition_text}

■ 審査基準:
1. シラバス整合性: IPAシラバスの出題趣旨に合致し、その用語の基本的な役割・動作原理・目的が正しく捉えられているか（○/△/×）
2. 技術正確性: 誤った説明、ハルシネーション、他の類似用語との混同がないか（○/△/×）
3. 初学者可読性: 専門用語で専門用語を説明するような堂々巡りを避け、初学者が直感的に理解できる文面か。また2〜3文（100〜150文字程度）で簡潔か（○/△/×）
"""

        time.sleep(0.3)
        try:
            res = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=OfficialDefEvaluation,
                    temperature=0.1
                )
            )
            ev: OfficialDefEvaluation = res.parsed
            if ev:
                nr = ws.max_row + 1
                ws.cell(row=nr, column=1, value=nr - 1)
                ws.cell(row=nr, column=2, value=term)
                ws.cell(row=nr, column=3, value=subcat)
                ws.cell(row=nr, column=4, value=definition_text)
                ws.cell(row=nr, column=5, value=ev.eval1_syllabus)
                ws.cell(row=nr, column=6, value=ev.eval2_accuracy)
                ws.cell(row=nr, column=7, value=ev.eval3_readability)
                ws.cell(row=nr, column=8, value=ev.comment)

                wb_eval.save(EVAL_FILE)
                existing.add(term)
                print(f" ✅ ({ev.eval1_syllabus}/{ev.eval2_accuracy}/{ev.eval3_readability})")
            else:
                print(" ⚠️ パース失敗")

        except Exception as e:
            print(f" ❌ エラー: {e}")

wb_eval.save(EVAL_FILE)
print("\n" + "=" * 60)
print(f"🎉 査読完了！ 結果を '{EVAL_FILE}' に保存しました。")
print("=" * 60)
