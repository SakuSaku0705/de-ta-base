import os
import openpyxl

EXCEL_FILE = "fe_study_master_23sheets.xlsx"

TARGET_CATEGORIES = [
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動"
]

if not os.path.exists(EXCEL_FILE):
    print(f"❌ ファイルが見つかりません: {EXCEL_FILE}")
    exit(1)

wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True, read_only=True)

print("\n" + "=" * 70)
print("📊 【FE-AI Tutor】重要7分野 コンテンツ生成・進捗可視化ダッシュボード")
print("=" * 70)
print(f"{'分野名':<16} | {'進捗バー':<22} | {'試験対策文':<12} | {'画像紐付':<8}")
print("-" * 70)

total_terms_all = 0
total_exam_all = 0
total_img_all = 0

for sheet in TARGET_CATEGORIES:
    if sheet not in wb.sheetnames:
        continue
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        continue
    headers = [str(c).strip() if c is not None else "" for c in rows[0]]
    if "term_name" not in headers:
        continue
    
    t_idx = headers.index("term_name")
    ep_idx = headers.index("exam_point_text") if "exam_point_text" in headers else -1
    img_idx = headers.index("image_path") if "image_path" in headers else -1
    
    total = 0
    ep_count = 0
    img_count = 0
    
    for r in rows[1:]:
        term = r[t_idx]
        if term is None or str(term).strip() in ["", "None", "nan"]:
            continue
        total += 1
        
        if ep_idx != -1 and r[ep_idx] and str(r[ep_idx]).strip() not in ["", "None", "nan"]:
            ep_count += 1
        if img_idx != -1 and r[img_idx] and str(r[img_idx]).strip() not in ["", "None", "nan"]:
            img_count += 1
            
    pct = (ep_count / total * 100) if total > 0 else 0
    bar_len = int(pct / 5)  # 20マス
    bar = "█" * bar_len + "░" * (20 - bar_len)
    
    short_sheet = sheet.split(". ")[-1]
    print(f"{short_sheet:<14} | [{bar}] {pct:>5.1f}% | {ep_count:>4} / {total:>4} 語 | {img_count:>4} 枚")
    
    total_terms_all += total
    total_exam_all += ep_count
    total_img_all += img_count

print("-" * 70)
total_pct = (total_exam_all / total_terms_all * 100) if total_terms_all > 0 else 0
total_bar_len = int(total_pct / 5)
total_bar = "█" * total_bar_len + "░" * (20 - total_bar_len)
print(f"{'【全7分野 合計】':<12} | [{total_bar}] {total_pct:>5.1f}% | {total_exam_all:>4} / {total_terms_all:>4} 語 | {total_img_all:>4} 枚")
print("=" * 70 + "\n")
