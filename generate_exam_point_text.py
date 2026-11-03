"""
【FE-AI Tutor】試験直結解説（exam_point_text）専用 高速自動生成スクリプト
- 対象: 未生成（空欄）の用語のみを自動検出して生成
- 安全性: 1件ごとに即時Excelへ保存、中断しても直前から再開可能
"""

import os
import sys
import time
import openpyxl
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
EXCEL_FILE = "fe_study_master_23sheets.xlsx"
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

class ExamPointResponse(BaseModel):
    key_phrase_1: str = Field(description="正解を見抜くキーワードや選択肢の頻出言い換えパターン（1文目）")
    key_phrase_2: str = Field(description="試験での着眼点や区別すべきポイント（2文目）")
    concept_point_1: str = Field(description="仕組み・データの集約や動作についての解説（1行目）")
    concept_point_2: str = Field(description="データの加工・安全性やアルゴリズムの動作解説（2行目）")
    concept_point_3: str = Field(description="利活用目的やメリットに関する解説（3行目）")
    concept_point_4: str = Field(description="試験で問われるポイントのまとめ（4行目）")

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("🔑 Google Cloud Vertex AI に接続しました。")
except Exception as e:
    print(f"❌ 認証クライアントの初期化エラー: {e}")
    sys.exit(1)

def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Excelファイルが見つかりません: {EXCEL_FILE}")
        return

    print(f"📖 {EXCEL_FILE} を読み込み中...")
    wb = openpyxl.load_workbook(EXCEL_FILE)

    total_generated = 0

    for sheet_name in TARGET_SHEETS:
        # 部分一致でシートを特定（前後の空白対策）
        matched_sheet = None
        for s in wb.sheetnames:
            if sheet_name in s:
                matched_sheet = s
                break

        if not matched_sheet:
            print(f"⚠️ シート '{sheet_name}' が見つかりません。スキップします。")
            continue

        ws = wb[matched_sheet]
        
        # ヘッダー列インデックスの特定
        headers = {}
        for col in range(1, ws.max_column + 1):
            val = ws.cell(row=1, column=col).value
            if val:
                headers[str(val).strip()] = col

        if "term_name" not in headers:
            print(f"⚠️ '{matched_sheet}' に 'term_name' 列がありません。")
            continue

        term_col = headers["term_name"]
        subcat_col = headers.get("sub_category")
        off_def_col = headers.get("kakomon_official_def")

        # exam_point_text 列がなければ追加
        if "exam_point_text" not in headers:
            exam_col = ws.max_column + 1
            ws.cell(row=1, column=exam_col, value="exam_point_text")
            headers["exam_point_text"] = exam_col
        else:
            exam_col = headers["exam_point_text"]

        # 未生成の行を抽出
        unprocessed_rows = []
        for r in range(2, ws.max_row + 1):
            term_val = ws.cell(row=r, column=term_col).value
            if not term_val or str(term_val).strip() in ["", "None", "nan"]:
                continue
            
            exam_val = ws.cell(row=r, column=exam_col).value
            if not exam_val or str(exam_val).strip() in ["", "None", "nan"]:
                unprocessed_rows.append(r)

        print(f"\n📂 【{matched_sheet}】: 未生成 {len(unprocessed_rows)} 件 / 全 {ws.max_row - 1} 行")

        if not unprocessed_rows:
            continue

        for idx, row in enumerate(unprocessed_rows, start=1):
            term = str(ws.cell(row=row, column=term_col).value).strip()
            subcat = str(ws.cell(row=row, column=subcat_col).value or matched_sheet).strip() if subcat_col else matched_sheet
            off_def = str(ws.cell(row=row, column=off_def_col).value or "").strip() if off_def_col else ""

            print(f"  [{idx}/{len(unprocessed_rows)}] 📝 生成中: {term} ...", end="", flush=True)
            start_t = time.time()

            prompt = f"""あなたは基本情報技術者試験（科目A）の指導のプロです。
初学者が過去問の正解肢・誤答肢を見抜けるようになるための「試験直結解説」を作成してください。
単なる日常の例え話ではなく、試験で問われる仕組みの動作やロジックを正確に説明してください。

【対象用語】: {term}
【分類】: {subcat}
【公式定義】: {off_def if off_def else 'シラバス標準定義'}

1. 【試験の決め手（正解を見抜くキーワード）】
- 過去問の選択肢で頻出する「言い換えパターン」や「正解・不正解を判定するキーワード」を1〜2文で明確に書いてください。

2. 【概念理解・試験の着眼点（図解連動テキスト）】
- なぜその仕組み・アルゴリズムが必要なのか、初学者が試験問題のロジックを理解できるように3〜4行で分かりやすく解説してください。
"""

            try:
                res = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExamPointResponse,
                        temperature=0.2
                    )
                )
                data: ExamPointResponse = res.parsed
                if data:
                    formatted_text = (
                        f"1. 【試験の決め手（正解を見抜くキーワード）】\n"
                        f"- {data.key_phrase_1}\n"
                        f"- {data.key_phrase_2}\n\n"
                        f"2. 【概念理解・試験の着眼点（図解連動テキスト）】\n"
                        f"- {data.concept_point_1}\n"
                        f"- {data.concept_point_2}\n"
                        f"- {data.concept_point_3}\n"
                        f"- {data.concept_point_4}"
                    )
                    ws.cell(row=row, column=exam_col, value=formatted_text)
                    elapsed = time.time() - start_t
                    print(f" ✅ 完了 ({elapsed:.2f}秒)")
                    total_generated += 1

                    # 1件ごとに即時Excel保存（破損防止・安全対策）
                    wb.save(EXCEL_FILE)
                else:
                    print(" ⚠️ パース失敗")

            except Exception as e:
                print(f" ❌ エラー: {e}")

            time.sleep(0.3)

    wb.save(EXCEL_FILE)
    print("\n" + "=" * 60)
    print(f"🎉 生成完了！ 新たに {total_generated} 件の試験対策テキストを書き込みました。")
    print("=" * 60)

if __name__ == "__main__":
    main()
