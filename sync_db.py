"""
【FE-AI Tutor】高精度・差分検知データベース同期スクリプト (sync_db.py)
- 重複用語の完全制御: 
    1. 重点7分野の定義を最優先採用
    2. 同一実行内での複数シートによる相互上書き（ピンポン現象）を完全排除
- 実際にデータが変更された用語のみを検知・更新
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
    parser.add_argument("--rebuild", action="store_true", help="【危険】テーブルを初期化して完全再構築する")
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
        print("\n⚠️ [--rebuild] 既存テーブルを初期化して再構築します...")
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

    cur.execute("PRAGMA table_info(terms);")
    cols = [c[1] for c in cur.fetchall()]
    target_cols = ["category", "sub_category", "official_def", "metaphor_def", "practical_ex", "exam_point_text", "url", "image_path"]
    for col_need in target_cols:
        if col_need not in cols:
            cur.execute(f"ALTER TABLE terms ADD COLUMN {col_need} TEXT;")

    print("\n🔍 [厳密差分同期] 重複排除と重点分野優先ルールを適用して差分を走査中...")

    # 1. 重点分野を最優先で処理するため、重点シートを先頭に並べる
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

    # 2. Excel全シートから「各用語の最新正本データ」を1件だけ決定（ピンポン防止）
    master_terms = {}

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

            # すでに上位優先のシートで採用済みの用語は無視（重複シートによる上書きループを完全阻止）
            if t in master_terms:
                continue

            master_terms[t] = {
                "category": gv(r, "category"),
                "sub_category": gv(r, "sub_category") or sheet,
                "official_def": gv(r, "kakomon_official_def") or gv(r, "official_def"),
                "metaphor_def": gv(r, "intuitive_def_final") or gv(r, "intuitive_def"),
                "practical_ex": gv(r, "practical_example_final") or gv(r, "practical_example"),
                "exam_point_text": gv(r, "exam_point_text"),
                "url": gv(r, "kakomon_url") or gv(r, "url"),
                "image_path": image_map.get(t, gv(r, "image_path"))
            }

    # 3. 確定した正本データとDBの現在値を1件ずつ比較
    new_terms_count = 0
    updated_terms_count = 0
    updated_fields_total = 0
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
            changed_log.append(f" ✨ [新規追加] {t}")
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
                updated_fields_total += len(diff_fields)
                cols_desc = ", ".join(diff_fields.keys())
                changed_log.append(f" 📝 [差分更新] {t} ({cols_desc})")

    conn.commit()
    conn.close()

    print("-" * 60)
    if changed_log:
        print(f"【変更詳細（全 {len(changed_log)} 件中 最新 15 件）】")
        for item in changed_log[:15]:
            print(item)
        if len(changed_log) > 15:
            print(f" ... 他 {len(changed_log) - 15} 件の変更あり")
        print("-" * 60)
        print(f"🎉 差分同期完了:")
        print(f" - 実質変更された用語: {updated_terms_count} 件（更新項目数: 計 {updated_fields_total} 箇所）")
        print(f" - 新規追加された用語: {new_terms_count} 件")
        print(f" - 変更なし（スキップ）: 保持されました")
    else:
        print("✨ データベースは既に最新の状態です（変更・差分はありませんでした）。")
    print("-" * 60)

if __name__ == "__main__":
    main()
