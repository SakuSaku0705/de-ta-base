"""
【FE-AI Tutor】IPAシラバス準拠 公式定義（official_def）高品質再生成スクリプト
- 進捗管理ファイル (official_def_progress.txt) による確実な再開制御:
  古い概要文を検知して確実に新プロンプトで上書きし、今回の実行で完了した分のみをスキップ
- 評価1（シラバス適合性）・評価2（工学的正確性・弁別性）特化型
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
PROGRESS_FILE = "official_def_progress.txt"
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
    definition: str = Field(description="IPAシラバスに完全に合致し、技術的誤謬のない厳密な公式定義文（2〜3文程度）")

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("🔑 Google Cloud Vertex AI に接続しました。")
except Exception as e:
    print(f"❌ 認証クライアントの初期化エラー: {e}")
    sys.exit(1)

def load_progress():
    """今回の新生成で完了した用語名セットを読み込む"""
    if not os.path.exists(PROGRESS_FILE):
        return set()
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def mark_done(term):
    """新生成完了を用語ごとに追記保存"""
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(term + "\n")

def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Excelファイルが見つかりません: {EXCEL_FILE}")
        return

    completed_terms = load_progress()
    print(f"📖 {EXCEL_FILE} を読み込み中...（今回の新生成 完了済み: {len(completed_terms)} 件）")
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
        def_col = headers.get("official_def") or headers.get("kakomon_official_def")
        
        if not def_col:
            def_col = ws.max_column + 1
            ws.cell(row=1, column=def_col, value="official_def")
            headers["official_def"] = def_col

        if not term_col:
            continue

        # 新プロンプトでまだ生成されていない用語だけを抽出
        target_rows = []
        for r in range(2, ws.max_row + 1):
            term_val = str(ws.cell(row=r, column=term_col).value or "").strip()
            if term_val and term_val not in ["None", "nan"] and term_val not in completed_terms:
                target_rows.append(r)

        if not target_rows:
            print(f"📂 【{matched_sheet}】: 新プロンプトでの生成完了済み（スキップ）")
            continue

        print(f"\n📂 【{matched_sheet}】: 新定義の生成対象 {len(target_rows)} 件 / 全 {ws.max_row - 1} 行")

        for idx, row in enumerate(target_rows, start=1):
            term = str(ws.cell(row=row, column=term_col).value).strip()
            subcat = str(ws.cell(row=row, column=subcat_col).value or matched_sheet).strip() if subcat_col else matched_sheet

            print(f"  [{idx}/{len(target_rows)}] 📝 厳密定義生成中: {term} ...", end="", flush=True)

            prompt = f"""あなたはIPA（情報処理推進機構）の基本情報技術者試験（科目A）シラバス策定委員および情報工学の学会員です。
対象用語に対する「厳密な公式定義（シラバス標準定義）」を作成してください。
※初学者向けの噛み砕いた解説（比喩や実例）は別画面で提供するため、ここでは一切不要です。専門的かつ学術的な厳密性を最優先してください。

【対象用語】: {term}
【分野・中分類】: {subcat}

■ 執筆基準（評価1・評価2特化要件）:
1. 【シラバス整合性（最重要）】: IPAシラバスの出題基準に完全準拠し、その用語が対象分野において「何を行うための技術・概念・規準か」「どのような目的・役割を持つか」を過不足なく明確に記述すること。
2. 【技術正確性（最重要）】: 類似概念や上位/下位概念（例: Wi-FiとBluetooth、ハッシュと暗号、排他制御とデッドロック等）との混同を完全に排除し、工学的に一切の誤謬・ハルシネーションがない厳格な記述とすること。
3. 【文体と構成】: 2〜3文程度（120〜160文字程度）で端正な辞書・教科書的文体（「〜とは、…である。」）にまとめること。
"""

            try:
                res = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=OfficialDefResponse,
                        temperature=0.0
                    )
                )
                data: OfficialDefResponse = res.parsed
                if data and data.definition:
                    cleaned_def = data.definition.strip()
                    ws.cell(row=row, column=def_col, value=cleaned_def)
                    if "kakomon_official_def" in headers:
                        ws.cell(row=row, column=headers["kakomon_official_def"], value=cleaned_def)
                    
                    # 進捗ファイルに書き込んで二重生成を防止
                    mark_done(term)
                    completed_terms.add(term)

                    print(" ✅")
                    total_generated += 1

                    if total_generated % 5 == 0:
                        wb.save(EXCEL_FILE)
                else:
                    print(" ⚠️ パース失敗")

            except Exception as e:
                print(f" ❌ エラー: {e}")

            time.sleep(0.2)

        wb.save(EXCEL_FILE)

    wb.save(EXCEL_FILE)
    print("\n" + "=" * 60)
    print(f"🎉 厳密公式定義の生成完了！ 今回生成: {total_generated} 件")
    print("=" * 60)

if __name__ == "__main__":
    main()
