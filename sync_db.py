"""
【FE-AI Tutor】高精度・差分検知データベース同期スクリプト (sync_db.py)
- terms テーブル（用語解説・画像パス）と terms_master テーブル（Q1・Q2問題）の両方を差分同期
"""

import os
import sys
import argparse
import sqlite3
import openpyxl

EXCEL_FILE = "fe_study_master_23sheets.xlsx"
DB_FILE = "fe_study.db"
IMAGE_DIR = "static/images"

TARGET_7_CATEGORIES = [
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動"
]

QUIZ_COLS = [
    "question_text", "choice_a", "choice_b", "choice_c", "choice_d", "correct_ans",
    "explanation_beginner", "explanation_advanced",
    "q2_question_text", "q2_choice_a", "q2_choice_b", "q2_choice_c", "q2_choice_d",
    "q2_correct_ans", "q2_exp_beginner_final", "q2_exp_advanced_final"
]

def scan_images():
    if not os.path.exists(IMAGE_DIR):
        return {}
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    m = {}
    for f in os.listdir(IMAGE_DIR):
        base, ext = os.path.splitext(f)
        if ext.lower() in valid_exts:
            m[base.strip()] = os.path.join(IMAGE_DIR, f)
    return m

def main():
    parser = argparse.ArgumentParser(description="FE-AI Tutor データベース同期スクリプト")
    parser.add_argument("--rebuild", action="store_true", help="【危険】termsテーブルを初期化して完全再構築する")
    args = parser.parse_args()

    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Excelファイルが見つかりません: {EXCEL_FILE}")
        sys.exit(1)

    image_map = scan_images()
    print(f"📸 検出画像数: {len(image_map)} 件")

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    print(f"📖 {EXCEL_FILE} を読み込み中...")
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)

    if args.rebuild:
        print("\n⚠️ [--rebuild] 既存termsテーブルを初期化して再構築します...")
        cur.execute("DROP TABLE IF EXISTS terms;")
        cur.execute("""
        CREATE TABLE terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_name TEXT UNIQUE NOT NULL,
            category TEXT,
            sub_category TEXT,
            metaphor_def TEXT,
            practical_ex TEXT,
            official_def TEXT,
            exam_point_text TEXT,
            url TEXT,
            image_path TEXT
        );
        """)

    # terms テーブルのカラム確認
    cur.execute("PRAGMA table_info(terms);")
    cols = [c[1] for c in cur.fetchall()]
    target_cols = ["category", "sub_category", "official_def", "metaphor_def", "practical_ex", "exam_point_text", "url", "image_path"]
    for col_need in target_cols:
        if col_need not in cols:
            cur.execute(f"ALTER TABLE terms ADD COLUMN {col_need} TEXT;")

    # terms_master テーブルの存在確認とカラム追加
    cur.execute("""
    CREATE TABLE IF NOT EXISTS terms_master (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term_name TEXT UNIQUE,
        sub_category TEXT
    );
    """)
    cur.execute("PRAGMA table_info(terms_master);")
    tm_cols = [c[1] for c in cur.fetchall()]
    for qcol in ["sub_category"] + QUIZ_COLS:
        if qcol not in tm_cols:
            cur.execute(f"ALTER TABLE terms_master ADD COLUMN {qcol} TEXT;")

    print("\n🔍 [厳密差分同期] 用語データ・画像・Q1/Q2問題の差分を走査中...")

    priority_sheets = []
    other_sheets = []
    for s in wb.sheetnames:
        if s in ["全用語一覧", "サマリー＆ガイドライン"]:
            continue
        if any(tc in s for tc in TARGET_7_CATEGORIES):
            priority_sheets.append(s)
        else:
            other_sheets.append(s)

    all_sheets = priority_sheets + other_sheets

    master_terms = {}
    master_quizzes = {}

    for sheet in all_sheets:
        ws = wb[sheet]
        headers = [c.value for c in ws[1] if c.value]
        if "term_name" not in headers:
            continue

        def gv(r, name):
            if name in headers:
                val = ws.cell(row=r, column=headers.index(name) + 1).value
                return str(val).strip() if val and str(val).strip() not in ["None", "nan"] else ""
            return ""

        for r in range(2, ws.max_row + 1):
            t = gv(r, "term_name")
            if not t:
                continue

            subcat = gv(r, "sub_category") or sheet

            if t not in master_terms:
                master_terms[t] = {
                    "category": gv(r, "category"),
                    "sub_category": subcat,
                    "official_def": gv(r, "kakomon_official_def") or gv(r, "official_def"),
                    "metaphor_def": gv(r, "intuitive_def_final") or gv(r, "intuitive_def"),
                    "practical_ex": gv(r, "practical_example_final") or gv(r, "practical_example"),
                    "exam_point_text": gv(r, "exam_point_text"),
                    "url": gv(r, "kakomon_url") or gv(r, "url"),
                    "image_path": image_map.get(t, gv(r, "image_path"))
                }

            # 問題データ（Q1 / Q2）の収集
            q_dict = {"sub_category": subcat}
            has_any_q = False
            for qcol in QUIZ_COLS:
                val = gv(r, qcol)
                if val:
                    q_dict[qcol] = val
                    has_any_q = True
            if has_any_q:
                if t not in master_quizzes:
                    master_quizzes[t] = q_dict
                else:
                    # すでに登録済みでも、空欄の列があれば補完する
                    for k, v in q_dict.items():
                        if v and not master_quizzes[t].get(k):
                            master_quizzes[t][k] = v

    # 1. terms テーブル（解説・画像）の差分更新
    new_terms_count = 0
    updated_terms_count = 0
    changed_log = []

    for t, excel_vals in master_terms.items():
        cur.execute("SELECT * FROM terms WHERE trim(term_name) = ?;", (t,))
        db_row = cur.fetchone()

        if not db_row:
            cols_str = ", ".join(["term_name"] + list(excel_vals.keys()))
            placeholders = ", ".join(["?"] * (len(excel_vals) + 1))
            values = [t] + list(excel_vals.values())
            cur.execute(f"INSERT INTO terms ({cols_str}) VALUES ({placeholders});", values)
            new_terms_count += 1
            changed_log.append(f" ✨ [用語追加] {t}")
        else:
            diff_fields = {}
            for col_name, new_val in excel_vals.items():
                if new_val != "":
                    old_val = str(db_row[col_name] or "").strip()
                    if old_val != new_val:
                        diff_fields[col_name] = new_val

            if diff_fields:
                set_clause = ", ".join([f"{k} = ?" for k in diff_fields.keys()])
                params = list(diff_fields.values()) + [t]
                cur.execute(f"UPDATE terms SET {set_clause} WHERE trim(term_name) = ?;", params)
                updated_terms_count += 1
                cols_desc = ", ".join(diff_fields.keys())
                changed_log.append(f" 📝 [用語更新] {t} ({cols_desc})")

    # 2. terms_master テーブル（Q1・Q2問題）の差分更新
    new_quiz_count = 0
    updated_quiz_count = 0

    for t, q_vals in master_quizzes.items():
        cur.execute("SELECT * FROM terms_master WHERE trim(term_name) = ?;", (t,))
        db_qrow = cur.fetchone()

        if not db_qrow:
            cols_str = ", ".join(["term_name"] + list(q_vals.keys()))
            placeholders = ", ".join(["?"] * (len(q_vals) + 1))
            values = [t] + list(q_vals.values())
            cur.execute(f"INSERT INTO terms_master ({cols_str}) VALUES ({placeholders});", values)
            new_quiz_count += 1
        else:
            diff_q = {}
            for col_name, new_val in q_vals.items():
                if new_val != "":
                    old_val = str(db_qrow[col_name] or "").strip()
                    if old_val != new_val:
                        diff_q[col_name] = new_val
            if diff_q:
                set_clause = ", ".join([f"{k} = ?" for k in diff_q.keys()])
                params = list(diff_q.values()) + [t]
                cur.execute(f"UPDATE terms_master SET {set_clause} WHERE trim(term_name) = ?;", params)
                updated_quiz_count += 1

    conn.commit()
    conn.close()

    print("-" * 60)
    if changed_log:
        print(f"【用語・画像の変更詳細（全 {len(changed_log)} 件中 最新 10 件）】")
        for item in changed_log[:10]:
            print(item)
        if len(changed_log) > 10:
            print(f" ... 他 {len(changed_log) - 10} 件の変更あり")
    print("-" * 60)
    print("🎉 データベース同期完了:")
    print(f" - 用語・画像（terms）      : 新規 {new_terms_count} 件 / 更新 {updated_terms_count} 件")
    print(f" - 演習問題（terms_master） : 新規 {new_quiz_count} 件 / 更新 {updated_quiz_count} 件")
    print("-" * 60)

if __name__ == "__main__":
    main()