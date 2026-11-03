"""
【FE-AI Tutor】総合自動生成スクリプト
使い方:
  python3 generate_all.py --mode q1       # Q1問題・属性別解説の生成
  python3 generate_all.py --mode q2       # Q2不適当選択問題の生成
  python3 generate_all.py --mode exam     # 試験対策テキストの生成
  python3 generate_all.py --mode diagram  # 16:9横長インフォグラフィック図解の生成
  python3 generate_all.py --mode all      # 全コンテンツの一括未生成分補完
"""

import os
import sys
import time
import argparse
import sqlite3
import openpyxl
from pydantic import BaseModel, Field
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from google import genai
from google.genai import types

plt.rcParams['font.family'] = 'Hiragino Sans'

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
EXCEL_FILE = "fe_study_master_23sheets.xlsx"
DB_FILE = "fe_study.db"
IMAGE_DIR = "static/images"
os.makedirs(IMAGE_DIR, exist_ok=True)

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

TARGET_CATEGORIES = [
    "3. コンピュータ構成要素", "5. ソフトウェア", "9. データベース",
    "10. ネットワーク", "11. セキュリティ", "12. システム開発技術", "22. 企業活動"
]

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"❌ Vertex AI 接続エラー: {e}")
    sys.exit(1)

# --- スキーマ定義 ---
class Q1Data(BaseModel):
    intuitive_def: str = Field(description="日常の比喩説明（2文程度）")
    practical_example: str = Field(description="身近なIT実務での活用事例（2文程度）")
    question_text: str = Field(description="4択問題文")
    correct_choice: str = Field(description="正解選択肢")
    dummy_choice_1: str = Field(description="誤答1")
    dummy_choice_2: str = Field(description="誤答2")
    dummy_choice_3: str = Field(description="誤答3")
    beg_summary: str
    beg_why_correct: str
    beg_why_dummy1: str
    beg_why_dummy2: str
    beg_why_dummy3: str
    adv_summary: str
    adv_why_correct: str
    adv_why_dummy1: str
    adv_why_dummy2: str
    adv_why_dummy3: str

class Q2Data(BaseModel):
    question_text: str = Field(description="『不適切なものを選べ』の4択問題文")
    wrong_choice: str = Field(description="正解（不適切な記述）")
    correct_fact_1: str = Field(description="ダミー1（適切な事実）")
    correct_fact_2: str = Field(description="ダミー2（適切な事実）")
    correct_fact_3: str = Field(description="ダミー3（適切な事実）")
    beg_summary: str
    beg_why_wrong: str
    beg_why_fact1: str
    beg_why_fact2: str
    beg_why_fact3: str
    adv_summary: str
    adv_why_wrong: str
    adv_why_fact1: str
    adv_why_fact2: str
    adv_why_fact3: str

class ExamPointData(BaseModel):
    key_phrase_1: str
    key_phrase_2: str
    concept_point_1: str
    concept_point_2: str
    concept_point_3: str
    concept_point_4: str

class DiagramInfo(BaseModel):
    english_name: str
    sub_title: str
    left_title: str
    left_points: list[str]
    center_action: str
    right_title: str
    right_points: list[str]
    exam_takeaway: str
    footer_tags: list[str]

# --- 描画関数 ---
def draw_infographic(term: str, d: DiagramInfo, path: str):
    fig, ax = plt.subplots(figsize=(16, 9), dpi=150)
    ax.set_facecolor('#F8FAFC')
    fig.patch.set_facecolor('#F8FAFC')

    ax.text(0.5, 0.94, term, ha='center', va='center', fontsize=26, weight='black', color='#0F172A')
    sub = f"({d.english_name})  ―  {d.sub_title}" if d.english_name else d.sub_title
    ax.text(0.5, 0.885, sub, ha='center', va='center', fontsize=12.5, color='#475569')

    # 左カード
    ax.add_patch(patches.FancyBboxPatch((0.05, 0.28), 0.38, 0.54, boxstyle="round,pad=0.02,rounding_size=0.03", fc="#FFFFFF", ec="#CBD5E1", lw=2, zorder=2))
    ax.add_patch(patches.FancyBboxPatch((0.05, 0.74), 0.38, 0.08, boxstyle="round,pad=0.02,rounding_size=0.02", fc="#EFF6FF", ec="#93C5FD", lw=1.5, zorder=3))
    ax.text(0.24, 0.78, d.left_title, ha='center', va='center', fontsize=14, weight='bold', color='#1E40AF', zorder=4)
    y = 0.67
    for pt in d.left_points[:4]:
        ax.text(0.08, y, f"• {pt}", fontsize=13, color='#1E293B', zorder=4)
        y -= 0.10

    # 中央矢印
    ax.annotate('', xy=(0.57, 0.55), xytext=(0.43, 0.55), arrowprops=dict(facecolor='#0284C7', edgecolor='#0369A1', width=6, headwidth=16, zorder=5))
    ax.add_patch(patches.FancyBboxPatch((0.44, 0.44), 0.12, 0.08, boxstyle="round,pad=0.015,rounding_size=0.02", fc="#E0F2FE", ec="#38BDF8", lw=1.5, zorder=6))
    ax.text(0.50, 0.48, f"⚙️ {d.center_action}", ha='center', va='center', fontsize=11, weight='bold', color='#0369A1', zorder=7)

    # 右カード
    ax.add_patch(patches.FancyBboxPatch((0.57, 0.28), 0.38, 0.54, boxstyle="round,pad=0.02,rounding_size=0.03", fc="#FFFFFF", ec="#CBD5E1", lw=2, zorder=2))
    ax.add_patch(patches.FancyBboxPatch((0.57, 0.74), 0.38, 0.08, boxstyle="round,pad=0.02,rounding_size=0.02", fc="#F0FDF4", ec="#86EFAC", lw=1.5, zorder=3))
    ax.text(0.76, 0.78, d.right_title, ha='center', va='center', fontsize=14, weight='bold', color='#166534', zorder=4)
    y = 0.67
    for pt in d.right_points[:4]:
        ax.text(0.60, y, f"✔ {pt}", fontsize=13, color='#1E293B', zorder=4)
        y -= 0.10

    # 下部バー ＆ タグ
    ax.add_patch(patches.FancyBboxPatch((0.05, 0.12), 0.90, 0.11, boxstyle="round,pad=0.02,rounding_size=0.02", fc="#FEF9C3", ec="#FACC15", lw=2, zorder=5))
    ax.text(0.5, 0.175, f"★ 試験攻略 memo: {d.exam_takeaway}", ha='center', va='center', fontsize=15, weight='black', color='#854D0E', zorder=6)
    ax.text(0.5, 0.045, "    ".join([f"🏷️ {t}" for t in d.footer_tags[:4]]), ha='center', va='center', fontsize=11, color='#64748B', weight='bold')

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(path, bbox_inches='tight', dpi=150)
    plt.close()

# --- 生成実行メイン ---
def main():
    parser = argparse.ArgumentParser(description="FE-AI Tutor 自動生成スクリプト")
    parser.add_argument("--mode", choices=["q1", "q2", "exam", "diagram", "all"], default="exam", help="生成対象モード")
    parser.add_argument("--limit", type=int, default=None, help="実行件数上限")
    args = parser.parse_args()

    wb = openpyxl.load_workbook(EXCEL_FILE)
    print(f"🚀 モード [{args.mode.upper()}] で生成処理を開始します...")

    count = 0
    symbols = ["ア", "イ", "ウ", "エ"]

    for sheet in TARGET_CATEGORIES:
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        headers = {c.value: idx for idx, c in enumerate(ws[1], start=1) if c.value}

        for r in range(2, ws.max_row + 1):
            if args.limit and count >= args.limit:
                break

            term = str(ws.cell(row=r, column=headers.get("term_name", 1)).value or "").strip()
            if not term or term in ["None", "nan"]:
                continue

            subcat = str(ws.cell(row=r, column=headers.get("sub_category", 1)).value or sheet).strip()
            off_def = str(ws.cell(row=r, column=headers.get("kakomon_official_def", 1)).value or "").strip()

            # ① 試験対策テキスト生成
            if args.mode in ["exam", "all"]:
                exp_col = headers.get("exam_point_text")
                if not exp_col:
                    exp_col = len(headers) + 1
                    ws.cell(row=1, column=exp_col, value="exam_point_text")
                    headers["exam_point_text"] = exp_col

                current_exp = str(ws.cell(row=r, column=exp_col).value or "").strip()
                if not current_exp or current_exp in ["None", "nan"]:
                    print(f"[{sheet}] 📝 試験対策テキスト生成: {term} ...", end="", flush=True)
                    p = f"【対象用語】: {term}\n【分類】: {subcat}\n過去問の正解キーワードと動作ロジック解説を作成してください。"
                    try:
                        res = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=p,
                            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=ExamPointData, temperature=0.2)
                        )
                        ed: ExamPointData = res.parsed
                        text = f"1. 【試験の決め手（正解を見抜くキーワード）】\n- {ed.key_phrase_1}\n- {ed.key_phrase_2}\n\n2. 【概念理解・試験の着眼点（図解連動テキスト）】\n- {ed.concept_point_1}\n- {ed.concept_point_2}\n- {ed.concept_point_3}\n- {ed.concept_point_4}"
                        ws.cell(row=r, column=exp_col, value=text)
                        print(" ✅ 完了")
                        count += 1
                        time.sleep(0.3)
                    except Exception as e:
                        print(f" ⚠️ エラー: {e}")

            # ② 16:9 図解画像生成
            if args.mode in ["diagram", "all"]:
                img_path = f"{IMAGE_DIR}/{term}.png"
                img_col = headers.get("image_path")
                if not img_col:
                    img_col = len(headers) + 1
                    ws.cell(row=1, column=img_col, value="image_path")
                    headers["image_path"] = img_col

                if not os.path.exists(img_path):
                    print(f"[{sheet}] 🖼️ 図解生成: {term} ...", end="", flush=True)
                    p = f"用語: {term}, 分類: {subcat}, 定義: {off_def}\n左右対比のインフォグラフィック構成要素を作成してください。"
                    try:
                        res = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=p,
                            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=DiagramInfo, temperature=0.2)
                        )
                        dinfo: DiagramInfo = res.parsed
                        draw_infographic(term, dinfo, img_path)
                        ws.cell(row=r, column=img_col, value=img_path)
                        print(" ✅ 完了")
                        count += 1
                        time.sleep(0.3)
                    except Exception as e:
                        print(f" ⚠️ エラー: {e}")

            # 5件ごとに保存
            if count > 0 and count % 5 == 0:
                wb.save(EXCEL_FILE)

    wb.save(EXCEL_FILE)
    print(f"\n🎉 処理が完了しました！（合計 {count} 件処理）")

if __name__ == "__main__":
    main()
