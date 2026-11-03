"""
【FE-AI Tutor】過去問道場 解説文ズレ・途切れ一括修正スクリプト
- 用語名とWebページの一致確認（ズレ防止）
- 全段落・箇条書きを改行保持で完全取得（途切れ防止）
- 安全なバックアップ自動作成
"""

import os
import sys
import time
import shutil
import openpyxl
import requests
from bs4 import BeautifulSoup

EXCEL_FILE = "fe_study_master_23sheets.xlsx"
BACKUP_FILE = "fe_study_master_23sheets_backup_scrape.xlsx"

TARGET_SHEETS = [
    "3. コンピュータ構成要素", "5. ソフトウェア", "9. データベース",
    "10. ネットワーク", "11. セキュリティ", "12. システム開発技術", "22. 企業活動"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def extract_full_explanation(soup):
    """過去問道場のページ構造から完全な解説文を抽出"""
    # パターン1: シラバス・用語辞典ページ (.ansbg または #mainCol 内の解説枠)
    comment_box = soup.find("div", class_="ansbg") or soup.find("div", id="mainCol") or soup.find("div", class_="content")
    
    if not comment_box:
        return None

    # 不要な広告やナビゲーション、ボタン要素を除去
    for tag in comment_box.find_all(["script", "style", "iframe", "ins", "button", "nav"]):
        tag.decompose()

    # 解説テキストが存在するブロックを探索
    target_area = comment_box.find("div", class_="comment") or comment_box.find("div", class_="ans_comment") or comment_box

    paragraphs = []
    # テキストブロックを改行を保持して抽出
    for elem in target_area.find_all(["p", "li", "h3", "h4"]):
        t = elem.get_text().strip()
        # 広告文や過去問ナビの文言を除外
        if t and not any(ng in t for ng in ["過去問道場", "公式LINE", "Tweet", "シェア", "問題番号"]):
            paragraphs.append(t)

    if paragraphs:
        return "\n\n".join(paragraphs)
    
    # 区分けタグがない場合のフォールバック
    raw_text = target_area.get_text(separator="\n").strip()
    clean_lines = [line.strip() for line in raw_text.splitlines() if line.strip() and not any(ng in line for ng in ["過去問道場", "Tweet"])]
    return "\n".join(clean_lines)

def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ {EXCEL_FILE} が見つかりません。")
        sys.exit(1)

    print(f"📦 バックアップを作成中: {BACKUP_FILE}")
    shutil.copyfile(EXCEL_FILE, BACKUP_FILE)

    wb = openpyxl.load_workbook(EXCEL_FILE)
    total_fixed = 0
    mismatch_count = 0

    for sheetname in TARGET_SHEETS:
        matched = [s for s in wb.sheetnames if sheetname in s]
        if not matched:
            continue
        ws = wb[matched[0]]
        print(f"\n📂 シート検証・修復中: 【{ws.title}】")

        headers = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1) if ws.cell(row=1, column=c).value}
        
        term_col = headers.get("term_name")
        url_col = headers.get("kakomon_url") or headers.get("url")
        def_col = headers.get("kakomon_official_def") or headers.get("official_def")

        if not term_col or not def_col:
            print("  ⚠️ 必要な列が見つかりません。スキップします。")
            continue

        for r in range(2, ws.max_row + 1):
            term = str(ws.cell(row=r, column=term_col).value or "").strip()
            if not term or term in ["None", "nan"]:
                continue

            url = str(ws.cell(row=r, column=url_col).value or "").strip() if url_col else ""
            current_def = str(ws.cell(row=r, column=def_col).value or "").strip()

            # URLが存在する場合に再検証
            if url and url.startswith("http"):
                try:
                    res = requests.get(url, headers=HEADERS, timeout=8)
                    if res.status_code != 200:
                        continue
                    res.encoding = res.apparent_encoding
                    soup = BeautifulSoup(res.text, "html.parser")

                    # ① 用語とページの照合（ズレ判定）
                    page_title = soup.find("title").get_text() if soup.find("title") else ""
                    h1_text = soup.find("h1").get_text() if soup.find("h1") else ""
                    
                    # 用語名がタイトルやh1に含まれていない場合、ズレの可能性あり
                    term_clean = term.split("(")[0].strip()
                    if term_clean not in page_title and term_clean not in h1_text:
                        print(f"  ⚠️ [ズレ検出] 用語: '{term}' vs ページ名: '{page_title[:25]}...'")
                        mismatch_count += 1
                        continue

                    # ② 完全な解説文を再抽出（途切れ修復）
                    full_def = extract_full_explanation(soup)
                    if full_def and len(full_def) > len(current_def):
                        ws.cell(row=r, column=def_col, value=full_def)
                        print(f"  ✅ [解説修復] {term}: {len(current_def)}文字 ➔ {len(full_def)}文字に拡張")
                        total_fixed += 1
                    
                    time.sleep(0.4)
                except Exception as e:
                    continue

        wb.save(EXCEL_FILE)

    wb.save(EXCEL_FILE)
    print("\n" + "=" * 55)
    print(f"🎉 修復完了！")
    print(f" - 完全な解説文へ拡張・修復: {total_fixed} 件")
    print(f" - 用語とページがズレていた件数: {mismatch_count} 件")
    print("=" * 55)

if __name__ == "__main__":
    main()
