import os
import json
import sqlite3

DB_FILE = "fe_study.db"
OUTPUT_JSON = "experiment_105_terms.json"

TARGET_7_CATEGORIES = [
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動",
]

def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT term_name, question_text, q2_question_text
        FROM terms_master
        WHERE question_text IS NOT NULL AND TRIM(question_text) != ''
    """)
    quiz_map = {r["term_name"].strip(): dict(r) for r in cur.fetchall()}

    selected_by_cat = {}
    all_selected_terms = []

    for cat in TARGET_7_CATEGORIES:
        cur.execute("""
            SELECT term_name, sub_category, image_path, metaphor_def, practical_ex
            FROM terms
            WHERE sub_category LIKE ?
        """, (f"%{cat}%",))
        rows = [dict(r) for r in cur.fetchall()]

        scored = []
        for r in rows:
            t = r["term_name"].strip()
            if t not in quiz_map:
                continue
            q_info = quiz_map[t]
            p = str(r.get("image_path") or "").strip()
            has_img = bool(p and p not in ("None", "nan") and os.path.exists(p))
            has_q2 = bool(q_info.get("q2_question_text") and str(q_info["q2_question_text"]).strip() not in ("", "None", "nan"))
            has_meta = bool(r.get("metaphor_def") and r.get("practical_ex"))

            # イラスト登録済みを最優先(100点)、次にQ2完備(10点)、比喩・実例完備(5点)
            score = (100 if has_img else 0) + (10 if has_q2 else 0) + (5 if has_meta else 0)
            scored.append((score, has_img, t))

        scored.sort(key=lambda x: (-x[0], x[2]))
        picked = scored[:15]

        selected_by_cat[cat] = [x[2] for x in picked]
        all_selected_terms.extend([x[2] for x in picked])
        img_cnt = sum(1 for x in picked if x[1])
        print(f"✅ {cat:<24}: {len(picked):>2} 用語選出（うちイラスト付き: {img_cnt:>2} 枚）")

    conn.close()

    out_data = {
        "total_count": len(all_selected_terms),
        "categories": selected_by_cat,
        "terms": all_selected_terms
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"🎉 計 {len(all_selected_terms)} 用語の確定リストを {OUTPUT_JSON} に保存しました！")

if __name__ == "__main__":
    main()