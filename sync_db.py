"""
【FE-AI Tutor】総合データベース同期スクリプト (sync_db.py)
- official_def（用語概要・公式定義）の差分更新・完全再構築に完全対応
"""

import os
import sys
import argparse
import sqlite3
import openpyxl

EXCEL_FILE = "fe_study_master_23sheets.xlsx"
DB_FILE = "fe_study.db"
IMAGE_DIR = "static/images"

def scan_images():
    """static/images 内の画像をスキャンして用語名とのマップを作成"""
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
    parser.add_argument("--rebuild", action="store_true", help="テーブルを一旦削除して完全再構築する")
    args = parser.parse_args()

    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Excelファイルが見つかりません: {EXCEL_FILE}")
        sys.exit(1)

    image_map = scan_images()
    print(f"📸 検出画像数: {len(image_map)} 件")

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    print(f"📖 {EXCEL_FILE} を読み込み中...")
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)

    # =========================================================
    # モード1: 完全再構築 (--rebuild)
    # =========================================================
    if args.rebuild:
        print("\n🧹 [--rebuild] 既存テーブルを初期化し、マスターExcelから完全再構築します...")
        cur.execute("DROP TABLE IF EXISTS terms;")
        cur.execute("DROP TABLE IF EXISTS terms_master;")

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

        cur.execute("""
        CREATE TABLE terms_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_name TEXT,
            category TEXT,
            sub_category TEXT,
            question_text TEXT,
            choice_a TEXT,
            choice_b TEXT,
            choice_c TEXT,
            choice_d TEXT,
            correct_ans TEXT,
            explanation_beginner TEXT,
            explanation_advanced TEXT,
            q2_question_text TEXT,
            q2_choice_a TEXT,
            q2_choice_b TEXT,
            q2_choice_c TEXT,
            q2_choice_d TEXT,
            q2_correct_ans TEXT,
            q2_exp_beginner_final TEXT,
            q2_exp_advanced_final TEXT
        );
        """)

        term_cnt = 0
        quiz_cnt = 0

        for sheet in wb.sheetnames:
            if sheet in ["全用語一覧", "サマリー＆ガイドライン"]:
                continue
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
                if not t: continue

                cat = gv(r, "category")
                subcat = gv(r, "sub_category") or sheet
                meta = gv(r, "intuitive_def_final") or gv(r, "intuitive_def")
                prac = gv(r, "practical_example_final") or gv(r, "practical_example")
                off = gv(r, "kakomon_official_def") or gv(r, "official_def")
                exam = gv(r, "exam_point_text")
                url = gv(r, "kakomon_url") or gv(r, "url")
                img = image_map.get(t, gv(r, "image_path"))

                cur.execute("""
                    INSERT OR REPLACE INTO terms (
                        term_name, category, sub_category, metaphor_def, practical_ex,
                        official_def, exam_point_text, url, image_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (t, cat, subcat, meta, prac, off, exam, url, img))
                term_cnt += 1

                q_text = gv(r, "question_text")
                if q_text:
                    cur.execute("""
                        INSERT INTO terms_master (
                            term_name, category, sub_category, question_text,
                            choice_a, choice_b, choice_c, choice_d, correct_ans,
                            explanation_beginner, explanation_advanced,
                            q2_question_text, q2_choice_a, q2_choice_b, q2_choice_c, q2_choice_d,
                            q2_correct_ans, q2_exp_beginner_final, q2_exp_advanced_final
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        t, cat, subcat, q_text,
                        gv(r, "choice_a"), gv(r, "choice_b"), gv(r, "choice_c"), gv(r, "choice_d"), gv(r, "correct_ans"),
                        gv(r, "exp_beginner_final"), gv(r, "exp_advanced_final"),
                        gv(r, "q2_question_text"), gv(r, "q2_choice_a"), gv(r, "q2_choice_b"), gv(r, "q2_choice_c"), gv(r, "q2_choice_d"),
                        gv(r, "q2_correct_ans"), gv(r, "q2_exp_beginner_final"), gv(r, "q2_exp_advanced_final")
                    ))
                    quiz_cnt += 1

        conn.commit()
        print("-" * 55)
        print(f"🎉 再構築完了: 用語 {term_cnt} 件 / 問題 {quiz_cnt} 件をDBに登録しました！")
        print("-" * 55)

    # =========================================================
    # モード2: 差分同期 (通常実行)
    # =========================================================
    else:
        print("\n⚡ [差分同期モード] 既存の学習ログを保持したまま、最新の公式定義・比喩・実例・試験対策文・画像を同期します...")

        # カラムの存在チェック（なければ自動新設）
        cur.execute("PRAGMA table_info(terms);")
        cols = [c[1] for c in cur.fetchall()]
        for col_need in ["official_def", "exam_point_text", "image_path", "metaphor_def", "practical_ex"]:
            if col_need not in cols:
                cur.execute(f"ALTER TABLE terms ADD COLUMN {col_need} TEXT;")
                print(f"✨ terms テーブルに '{col_need}' カラムを追加しました。")

        updated = 0
        for sheet in wb.sheetnames:
            if sheet in ["全用語一覧", "サマリー＆ガイドライン"]:
                continue
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
                if not t: continue

                off = gv(r, "kakomon_official_def") or gv(r, "official_def")
                meta = gv(r, "intuitive_def_final") or gv(r, "intuitive_def")
                prac = gv(r, "practical_example_final") or gv(r, "practical_example")
                exam = gv(r, "exam_point_text")
                img = image_map.get(t, gv(r, "image_path"))

                # official_def も含めて差分同期
                cur.execute("""
                    UPDATE terms 
                    SET official_def = COALESCE(NULLIF(?, ''), official_def),
                        metaphor_def = COALESCE(NULLIF(?, ''), metaphor_def),
                        practical_ex = COALESCE(NULLIF(?, ''), practical_ex),
                        exam_point_text = COALESCE(NULLIF(?, ''), exam_point_text),
                        image_path = COALESCE(NULLIF(?, ''), image_path)
                    WHERE trim(term_name) = ?;
                """, (off, meta, prac, exam, img, t))
                updated += cur.rowcount

        conn.commit()
        print("-" * 55)
        print(f"🎉 差分同期完了: {updated} 箇所のデータを最新化しました！")
        print("-" * 55)

    conn.close()

if __name__ == "__main__":
    main()
