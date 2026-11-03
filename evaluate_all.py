"""
【FE-AI Tutor】総合品質査読スクリプト
使い方:
  python3 evaluate_all.py --target metaphor   # 日常の比喩・実社会での活用例の3軸査読
  python3 evaluate_all.py --target exam       # 試験直結解説の妥当性査読
  python3 evaluate_all.py --target question   # 4択問題・属性別解説のファクトチェック
"""

import os
import sys
import time
import argparse
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from typing import Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"
MASTER_FILE = "fe_study_master_23sheets.xlsx"

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

TARGET_SHEETS = [
    "3. コンピュータ構成要素", "5. ソフトウェア", "9. データベース",
    "10. ネットワーク", "11. セキュリティ", "12. システム開発技術", "22. 企業活動"
]

class MetaphorEval(BaseModel):
    eval1: Literal["○", "△", "×"] = Field(description="比喩の身近さ")
    eval2: Literal["○", "△", "×"] = Field(description="実用例の具体性")
    eval3: Literal["○", "△", "×"] = Field(description="技術正確性")
    comment: str

class ExamPointEval(BaseModel):
    eval1: Literal["○", "△", "×"] = Field(description="正解キーワード妥当性")
    eval2: Literal["○", "△", "×"] = Field(description="動作ロジック理解度")
    eval3: Literal["○", "△", "×"] = Field(description="技術正確性")
    comment: str

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"❌ Vertex AI 接続エラー: {e}")
    sys.exit(1)

def evaluate_session(mode: str):
    if mode == "metaphor":
        eval_file = "比喩・実用例_品質精査評価シート.xlsx"
        headers = ["No", "用語名", "中分類", "直感理解（日常の比喩）", "実社会での活用例", "【評価1】比喩の身近さ", "【評価2】実用例の具体性", "【評価3】技術正確性", "指摘事項・改善案コメント"]
    else:
        eval_file = "試験直結解説_品質精査評価シート.xlsx"
        headers = ["No", "用語名", "中分類", "試験直結解説（exam_point_text）", "【評価1】正解キーワード妥当性", "【評価2】動作ロジック理解度", "【評価3】技術正確性", "指摘事項・改善案コメント"]

    wb_eval = openpyxl.load_workbook(eval_file) if os.path.exists(eval_file) else openpyxl.Workbook()
    wb_master = openpyxl.load_workbook(MASTER_FILE, data_only=True)

    for sheet in TARGET_SHEETS:
        if sheet not in wb_master.sheetnames:
            continue
        ws_m = wb_master[sheet]
        ws_eval_title = f"{sheet} 査読"

        if ws_eval_title in wb_eval.sheetnames:
            ws_e = wb_eval[ws_eval_title]
        else:
            ws_e = wb_eval.create_sheet(title=ws_eval_title)
            for c_idx, h in enumerate(headers, 1):
                ws_e.cell(row=1, column=c_idx, value=h)

        existing = set()
        for r in range(2, ws_e.max_row + 1):
            t_val = ws_e.cell(row=r, column=2).value
            if t_val and ws_e.cell(row=r, column=6).value:
                existing.add(str(t_val).strip())

        m_headers = {c.value: idx for idx, c in enumerate(ws_m[1], 1) if c.value}

        for r in range(2, ws_m.max_row + 1):
            term = str(ws_m.cell(row=r, column=m_headers.get("term_name", 1)).value or "").strip()
            if not term or term in existing:
                continue

            subcat = str(ws_m.cell(row=r, column=m_headers.get("sub_category", 1)).value or sheet).strip()

            if mode == "metaphor":
                meta = str(ws_m.cell(row=r, column=m_headers.get("intuitive_def_final", 1)).value or "").strip()
                prac = str(ws_m.cell(row=r, column=m_headers.get("practical_example_final", 1)).value or "").strip()
                if not meta: continue
                prompt = f"用語: {term}, 分類: {subcat}\n比喩: {meta}\n実例: {prac}\n3軸で評価してください。"
                schema = MetaphorEval
            else:
                exam = str(ws_m.cell(row=r, column=m_headers.get("exam_point_text", 1)).value or "").strip()
                if not exam: continue
                prompt = f"用語: {term}, 分類: {subcat}\n解説文: {exam}\n3軸で評価してください。"
                schema = ExamPointEval

            print(f"[{sheet}] 🧐 査読中: {term} ...", end="", flush=True)
            try:
                res = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.1)
                )
                ev = res.parsed
                nr = ws_e.max_row + 1
                if mode == "metaphor":
                    vals = [nr - 1, term, subcat, meta, prac, ev.eval1, ev.eval2, ev.eval3, ev.comment]
                else:
                    vals = [nr - 1, term, subcat, exam, ev.eval1, ev.eval2, ev.eval3, ev.comment]

                for c_idx, v in enumerate(vals, 1):
                    ws_e.cell(row=nr, column=c_idx, value=v)

                wb_eval.save(eval_file)
                existing.add(term)
                print(f" ✅ ({ev.eval1}/{ev.eval2}/{ev.eval3})")
                time.sleep(0.5)
            except Exception as e:
                print(f" ⚠️ エラー: {e}")

    wb_eval.save(eval_file)
    print(f"\n🎉 査読結果を '{eval_file}' に保存しました！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["metaphor", "exam"], default="metaphor")
    args = parser.parse_args()
    evaluate_session(args.target)
