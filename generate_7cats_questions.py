"""
【FE-AI Tutor】重点7分野 一括 Q1・Q2問題補完生成 ＆ DB即時反映スクリプト
- 特徴1: 重点7分野のシートを順番に走査し、未生成のQ1・Q2のみを自動生成（既存分はDBから復元スキップ）
- 特徴2: 一時ファイル経由の原子保存（os.replace）により、中断してもExcelファイルが破損しない安全設計
"""

import os
import sys
import time
import random
import sqlite3
import openpyxl
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
EXCEL_FILE = "fe_study_master_23sheets.xlsx"
DB_FILE = "fe_study.db"
MODEL_NAME = "gemini-2.5-flash"

# 対象の重点分野キーワード（不足している分野を含む7分野）
TARGET_SHEET_KEYWORDS = [
    "3. コンピュータ構成要素",
    "4. システム構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動",
]

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print("🔑 Google Cloud Vertex AI に接続しました。")
except Exception as e:
    print(f"❌ 認証クライアントの初期化エラー: {e}")
    sys.exit(1)

class Q1Response(BaseModel):
    question_text: str = Field(description="基本情報技術者試験（科目A）形式の4択問題文（適切な記述・用語を選ばせる形式）")
    correct_choice: str = Field(description="正解の選択肢テキスト（記号なし）")
    dummy_choice_1: str = Field(description="誤答の選択肢テキスト1（記号なし）")
    dummy_choice_2: str = Field(description="誤答の選択肢テキスト2（記号なし）")
    dummy_choice_3: str = Field(description="誤答の選択肢テキスト3（記号なし）")
    beg_summary: str = Field(description="初学者向けの結論・ポイント要約（1〜2文）")
    beg_why_correct: str = Field(description="初学者向けの正解理由の平易な解説")
    beg_why_dummy: str = Field(description="初学者向けの誤答選択肢がなぜ違うかの解説")
    adv_summary: str = Field(description="実務・情報工学等の観点からの専門的要約")
    adv_why_correct: str = Field(description="専門的・技術的観点からの正解根拠の詳細解説")
    adv_why_dummy: str = Field(description="各誤答選択肢と対象用語の厳密な違いの解説")

class Q2Response(BaseModel):
    question_text: str = Field(description="『〜について、不適切なものはどれか』形式の4択問題文")
    wrong_choice: str = Field(description="正解となる『不適切な記述』の選択肢テキスト（記号なし）")
    correct_fact_1: str = Field(description="ダミー1：対象用語に関する『適切な事実』の記述（記号なし）")
    correct_fact_2: str = Field(description="ダミー2：対象用語に関する『適切な事実』の記述（記号なし）")
    correct_fact_3: str = Field(description="ダミー3：対象用語に関する『適切な事実』の記述（記号なし）")
    beg_summary: str = Field(description="初学者向けの結論・不適切な箇所のポイント要約")
    beg_why_wrong: str = Field(description="なぜその選択肢が不適切（誤り）なのかの分かりやすい解説")
    beg_why_facts: str = Field(description="他の3つの選択肢が正しい記述であることの補足説明")
    adv_summary: str = Field(description="専門的・技術的観点からのまとめ")
    adv_why_wrong: str = Field(description="不適切な選択肢のどこが技術・理論・制度上誤っているかの詳細解説")

def safe_save_workbook(wb, filepath):
    """一時ファイルに書き出してからリネームすることで、中断時のExcel破損を完全に防ぐ"""
    tmp_path = filepath + ".tmp.xlsx"
    wb.save(tmp_path)
    os.replace(tmp_path, filepath)

def get_or_create_col(ws, headers, col_name):
    if col_name not in headers:
        new_col = ws.max_column + 1
        ws.cell(row=1, column=new_col, value=col_name)
        headers[col_name] = new_col
    return headers[col_name]

def fetch_existing_db_questions(conn):
    """SQLiteにすでに保存済みのQ1/Q2問題データを辞書で取得する"""
    if not conn:
        return {}
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(terms_master)")
    cols = [c[1] for c in cur.fetchall()]
    if not cols:
        return {}
    cur.execute("SELECT * FROM terms_master")
    existing = {}
    for row in cur.fetchall():
        d = dict(zip(cols, row))
        tname = str(d.get("term_name") or "").strip()
        if tname:
            existing[tname] = d
    return existing

def sync_row_to_sqlite(conn, row_data):
    """生成した1用語分の問題データをSQLiteのterms_masterテーブルへ即時反映（UPSERT）する"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(terms_master)")
    db_cols = {c[1] for c in cur.fetchall()}
    if not db_cols:
        return

    valid_data = {k: v for k, v in row_data.items() if k in db_cols and v is not None}
    term_name = valid_data.get("term_name")
    if not term_name:
        return

    cur.execute("SELECT COUNT(*) FROM terms_master WHERE term_name = ?", (term_name,))
    exists = cur.fetchone()[0] > 0

    if exists:
        update_cols = [k for k in valid_data.keys() if k != "term_name"]
        set_clause = ", ".join([f"{k} = ?" for k in update_cols])
        vals = [valid_data[k] for k in update_cols] + [term_name]
        cur.execute(f"UPDATE terms_master SET {set_clause} WHERE term_name = ?", vals)
    else:
        cols_str = ", ".join(valid_data.keys())
        placeholders = ", ".join(["?"] * len(valid_data))
        cur.execute(f"INSERT INTO terms_master ({cols_str}) VALUES ({placeholders})", list(valid_data.values()))

    conn.commit()

def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Excelファイルが見つかりません: {EXCEL_FILE}")
        return

    print(f"📖 {EXCEL_FILE} を読み込み中...")
    wb = openpyxl.load_workbook(EXCEL_FILE)

    matched_sheets = []
    for kw in TARGET_SHEET_KEYWORDS:
        for s in wb.sheetnames:
            if kw in s and s not in matched_sheets:
                matched_sheets.append(s)

    if not matched_sheets:
        print("❌ 対象シートが見つかりません。")
        return

    conn = sqlite3.connect(DB_FILE) if os.path.exists(DB_FILE) else None
    existing_db = fetch_existing_db_questions(conn)

    needed_cols = [
        "question_text", "choice_a", "choice_b", "choice_c", "choice_d", "correct_ans",
        "explanation_beginner", "explanation_advanced",
        "q2_question_text", "q2_choice_a", "q2_choice_b", "q2_choice_c", "q2_choice_d",
        "q2_correct_ans", "q2_exp_beginner_final", "q2_exp_advanced_final"
    ]

    symbols = ["ア", "イ", "ウ", "エ"]
    rng = random.Random(20261124)

    total_q1_cnt = 0
    total_q2_cnt = 0
    total_restored_cnt = 0

    for sheet_name in matched_sheets:
        ws = wb[sheet_name]
        headers = {str(ws.cell(row=1, column=c).value).strip(): c for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value}

        if "term_name" not in headers:
            print(f"⚠️ シート '{sheet_name}' に 'term_name' 列がないためスキップします。")
            continue

        for cname in needed_cols:
            get_or_create_col(ws, headers, cname)

        total_rows = ws.max_row - 1
        print("\n" + "=" * 60)
        print(f"📂 【{sheet_name}】: 全 {total_rows} 用語をチェックします...")
        print("=" * 60)

        sheet_q1 = 0
        sheet_q2 = 0
        sheet_skip = 0

        for r in range(2, ws.max_row + 1):
            term = str(ws.cell(row=r, column=headers["term_name"]).value or "").strip()
            if not term or term in ["None", "nan"]:
                continue

            # SQLiteに保存済みのデータがあればExcel側にも書き戻す
            if term in existing_db:
                db_rec = existing_db[term]
                for cname in needed_cols:
                    val = db_rec.get(cname)
                    if val and str(val).strip() not in ["", "None", "nan"]:
                        ws.cell(row=r, column=headers[cname], value=val)

            subcat = str(ws.cell(row=r, column=headers.get("sub_category", 1)).value or sheet_name).strip()
            off_def = str(ws.cell(row=r, column=headers.get("official_def", headers.get("kakomon_official_def", 1))).value or "").strip()

            cur_q1 = str(ws.cell(row=r, column=headers["question_text"]).value or "").strip()
            cur_q2 = str(ws.cell(row=r, column=headers["q2_question_text"]).value or "").strip()

            need_q1 = not cur_q1 or cur_q1 in ["None", "nan"]
            need_q2 = not cur_q2 or cur_q2 in ["None", "nan"]

            if not need_q1 and not need_q2:
                sheet_skip += 1
                total_restored_cnt += 1
                continue

            print(f"[{r-1}/{total_rows}] 📌 {term} :", end="", flush=True)
            row_payload = {"term_name": term, "sub_category": subcat}

            # --- Q1（基本・正解選択問題）の生成 ---
            if need_q1:
                print(" [Q1生成中...", end="", flush=True)
                prompt_q1 = f"""あなたは基本情報技術者試験（科目A）の出題委員です。
分類「{sheet_name}」の重要用語に関する4択問題（適切なものを選ぶ形式）を作成してください。

【対象用語】: {term}
【分類】: {subcat}
【公式定義】: {off_def}

■ 要件:
1. 実際の基本情報技術者試験（科目A）の過去問レベルで、用語の意味や仕組み・役割を問う問題文にすること。
2. 4つの選択肢（正解1つ、紛らわしい誤答3つ）は文体や長さを揃えること。選択肢の先頭に「ア：」などの記号は付けないこと。
3. 初学者向け解説（平易な表現）と専門的詳細解説（情報工学・実務等の背景を含む）の両方を作成すること。
"""
                try:
                    res1 = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=prompt_q1,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=Q1Response,
                            temperature=0.25
                        )
                    )
                    d1: Q1Response = res1.parsed
                    if d1:
                        choices_pool = [
                            (d1.correct_choice.strip(), True),
                            (d1.dummy_choice_1.strip(), False),
                            (d1.dummy_choice_2.strip(), False),
                            (d1.dummy_choice_3.strip(), False)
                        ]
                        rng.shuffle(choices_pool)
                        ans_sym = "ア"
                        for i, (txt, is_c) in enumerate(choices_pool):
                            if is_c:
                                ans_sym = symbols[i]

                        exp_beg = f"【ポイント】{d1.beg_summary}\n\n【正解の理由】{d1.beg_why_correct}\n\n【誤答の解説】{d1.beg_why_dummy}"
                        exp_adv = f"【専門的要点】{d1.adv_summary}\n\n【根拠詳細】{d1.adv_why_correct}\n\n【他選択肢との比較】{d1.adv_why_dummy}"

                        q1_dict = {
                            "question_text": d1.question_text.strip(),
                            "choice_a": choices_pool[0][0],
                            "choice_b": choices_pool[1][0],
                            "choice_c": choices_pool[2][0],
                            "choice_d": choices_pool[3][0],
                            "correct_ans": ans_sym,
                            "explanation_beginner": exp_beg,
                            "explanation_advanced": exp_adv
                        }
                        for k, v in q1_dict.items():
                            ws.cell(row=r, column=headers[k], value=v)
                        row_payload.update(q1_dict)
                        sheet_q1 += 1
                        total_q1_cnt += 1
                        print("完了]", end="", flush=True)
                except Exception as e:
                    print(f"失敗:{e}]", end="", flush=True)
                time.sleep(0.3)

            # --- Q2（応用・不適当選択問題）の生成 ---
            if need_q2:
                print(" [Q2生成中...", end="", flush=True)
                prompt_q2 = f"""あなたは基本情報技術者試験（科目A）の出題委員です。
分類「{sheet_name}」の重要用語について、「不適切な記述を1つ選ぶ（誤りを見抜く）」形式の4択問題を作成してください。

【対象用語】: {term}
【分類】: {subcat}
【公式定義】: {off_def}

■ 要件:
1. 問題文は「{term}に関する記述として、最も不適切なものはどれか。」のような形式にすること。
2. 正解となる『不適切な記述』1つと、ダミーとなる『適切な事実の記述』3つを作成すること（記号は付けない）。
3. 初学者向け解説と専門的詳細解説を作成すること。
"""
                try:
                    res2 = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=prompt_q2,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=Q2Response,
                            temperature=0.25
                        )
                    )
                    d2: Q2Response = res2.parsed
                    if d2:
                        choices2_pool = [
                            (d2.wrong_choice.strip(), True),
                            (d2.correct_fact_1.strip(), False),
                            (d2.correct_fact_2.strip(), False),
                            (d2.correct_fact_3.strip(), False)
                        ]
                        rng.shuffle(choices2_pool)
                        ans2_sym = "ア"
                        for i, (txt, is_w) in enumerate(choices2_pool):
                            if is_w:
                                ans2_sym = symbols[i]

                        exp2_beg = f"【ポイント】{d2.beg_summary}\n\n【不適切な理由】{d2.beg_why_wrong}\n\n【他の選択肢について】{d2.beg_why_facts}"
                        exp2_adv = f"【専門的要点】{d2.adv_summary}\n\n【誤りの詳細根拠】{d2.adv_why_wrong}"

                        q2_dict = {
                            "q2_question_text": d2.question_text.strip(),
                            "q2_choice_a": choices2_pool[0][0],
                            "q2_choice_b": choices2_pool[1][0],
                            "q2_choice_c": choices2_pool[2][0],
                            "q2_choice_d": choices2_pool[3][0],
                            "q2_correct_ans": ans2_sym,
                            "q2_exp_beginner_final": exp2_beg,
                            "q2_exp_advanced_final": exp2_adv
                        }
                        for k, v in q2_dict.items():
                            ws.cell(row=r, column=headers[k], value=v)
                        row_payload.update(q2_dict)
                        sheet_q2 += 1
                        total_q2_cnt += 1
                        print("完了]", end="", flush=True)
                except Exception as e:
                    print(f"失敗:{e}]", end="", flush=True)
                time.sleep(0.3)

            print("")
            # 安全な一時ファイル経由でExcel保存 ＆ SQLite同期
            safe_save_workbook(wb, EXCEL_FILE)
            if conn and len(row_payload) > 2:
                sync_row_to_sqlite(conn, row_payload)

        print(f"👉 【{sheet_name}】完了: スキップ {sheet_skip} 件 / 新規 Q1: {sheet_q1} 問, Q2: {sheet_q2} 問")

    if conn:
        conn.close()
    safe_save_workbook(wb, EXCEL_FILE)

    print("\n" + "=" * 60)
    print("🎉 重点分野の問題補完生成とDB同期がすべて完了しました！")
    print(f"   既存スキップ: {total_restored_cnt} 用語 / 今回新規生成 Q1: {total_q1_cnt} 問, Q2: {total_q2_cnt} 問")
    print("=" * 60)

if __name__ == "__main__":
    main()