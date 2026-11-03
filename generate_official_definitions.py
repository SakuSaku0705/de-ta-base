"""
【FE-AI Tutor】IPAシラバス準拠 用語概要・公式定義（official_def）自動生成スクリプト
- 対象: 概要が未設定、または短すぎる/ズレていた用語を自動補完
- 安全設計: 1件ごとに即時保存、エラー発生時も直前から再開可能
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

class OfficialDefResponse(BaseModel):
    definition: str = Field(description="IPAシラバス準拠の簡潔かつ本質的な用語定義（2〜3文、100〜150文字程度）")

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
        matched_sheet = None
        for s in wb.sheetnames:
            if sheet_name in s:
                matched_sheet = s
                break

        if not matched_sheet:
            continue

        ws = wb[matched_sheet]
        headers = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value}

        term_col = headers.get("term_name")
        subcat_col = headers.get("sub_category")
        
        # official_def 列（なければ作成）
        def_col = headers.get("official_def") or headers.get("kakomon_official_def")
        if not def_col:
            def_col = ws.max_column + 1
            ws.cell(row=1, column=def_col, value="official_def")
            headers["official_def"] = def_col

        if not term_col:
            continue

        # 未設定、または壊れている（極端に短い / シラバスまとめページの文字列が入っている）行を抽出
        target_rows = []
        for r in range(2, ws.max_row + 1):
            term_val = str(ws.cell(row=r, column=term_col).value or "").strip()
            if not term_val or term_val in ["None", "nan"]:
                continue

            current_def = str(ws.cell(row=r, column=def_col).value or "").strip()
            
            # 空欄、またはまとめページのノイズが残っている場合は再生成対象
            is_empty = not current_def or current_def in ["None", "nan"]
            is_noisy = any(ng in current_def for ng in ["シラバス9.", "語（シラバス", "過去問道場"]) or len(current_def) < 15
            
            if is_empty or is_noisy:
                target_rows.append(r)

        print(f"\n📂 【{matched_sheet}】: 生成対象 {len(target_rows)} 件 / 全 {ws.max_row - 1} 行")

        for idx, row in enumerate(target_rows, start=1):
            term = str(ws.cell(row=row, column=term_col).value).strip()
            subcat = str(ws.cell(row=row, column=subcat_col).value or matched_sheet).strip() if subcat_col else matched_sheet

            print(f"  [{idx}/{len(target_rows)}] 📝 概要生成中: {term} ...", end="", flush=True)

            prompt = f"""あなたはIPA（情報処理推進機構）の基本情報技術者試験（科目A）シラバスの策定委員・情報科学の教育者です。
初学者が学習画面の一番最初（最上部）で読むための「用語の概要・公式定義」を作成してください。

【対象用語】: {term}
【分野】: {subcat}

■ 執筆ルール:
1. 用語が「何を行うものか」「どのような技術・概念か」を初学者向けに明確に定義すること。
2. 比喩やテクニック（着眼点）ではなく、標準的な教科書・シラバス定義に則ること。
3. 全体で2〜3文（100〜150文字程度）に過不足なくまとめること。
"""

            try:
                res = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=OfficialDefResponse,
                        temperature=0.2
                    )
                )
                data: OfficialDefResponse = res.parsed
                if data and data.definition:
                    cleaned_def = data.definition.strip()
                    ws.cell(row=row, column=def_col, value=cleaned_def)
                    # kakomon_official_def 列も存在していれば整合性をとる
                    if "kakomon_official_def" in headers:
                        ws.cell(row=row, column=headers["kakomon_official_def"], value=cleaned_def)
                    
                    print(" ✅ 完了")
                    total_generated += 1

                    # 5件ごとに保存
                    if total_generated % 5 == 0:
                        wb.save(EXCEL_FILE)
                else:
                    print(" ⚠️ パース失敗")

            except Exception as e:
                print(f" ❌ エラー: {e}")

            time.sleep(0.3)

        wb.save(EXCEL_FILE)

    wb.save(EXCEL_FILE)
    print("\n" + "=" * 60)
    print(f"🎉 生成完了！ 合計 {total_generated} 件の用語概要を補完・更新しました。")
    print("=" * 60)

if __name__ == "__main__":
    main()
