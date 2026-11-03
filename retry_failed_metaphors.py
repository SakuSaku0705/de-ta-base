import os
import sys
import time
import json
import sqlite3
import openpyxl
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

CREDENTIALS_JSON = "gcp_key.json"
PROJECT_ID = "gen-lang-client-0984224626"
LOCATION = "us-central1"

if os.path.exists(CREDENTIALS_JSON):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(CREDENTIALS_JSON)

EXCEL_MASTER = "fe_study_master_23sheets.xlsx"
EXCEL_EVAL = "比喩・実用例_品質精査評価シート.xlsx"
DB_FILE = "fe_study.db"
MODEL_NAME = "gemini-2.5-flash"

# --- スキーマ定義 ---
class RewriteResponse(BaseModel):
    metaphor: str = Field(description="専門用語を完全に排除した日常の比喩（料理・学校・買い物など。200〜300字）")
    practical_example: str = Field(description="実社会での身近なサービス例（LINE、Amazon、ATMなど。200〜300字）")

class EvaluationResponse(BaseModel):
    eval1_metaphor: str = Field(description="【評価1】比喩の身近さ（○, △, ×）")
    eval2_practical: str = Field(description="【評価2】実用例の具体性（○, △, ×）")
    eval3_accuracy: str = Field(description="【評価3】技術正確性（○, △, ×）")
    feedback: str = Field(description="改善コメントまたは評価理由")

try:
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
except Exception as e:
    print(f"❌ 認証クライアントの初期化に失敗しました: {e}")
    sys.exit(1)

def run_retry():
    if not os.path.exists(EXCEL_EVAL) or not os.path.exists(EXCEL_MASTER):
        print("❌ 必要なExcelファイルが見つかりません。")
        return

    print("📖 評価シートとマスターExcelを読み込み中...")
    wb_eval = openpyxl.load_workbook(EXCEL_EVAL)
    wb_master = openpyxl.load_workbook(EXCEL_MASTER)
    
    conn = sqlite3.connect(DB_FILE) if os.path.exists(DB_FILE) else None

    # 不合格対象の抽出
    targets = [] # (sheet_eval, row_eval, term_name, category, old_feedback)

    for s_eval in wb_eval.sheetnames:
        ws_eval = wb_eval[s_eval]
        cat_name = s_eval.replace(" 査読", "")

        for r in range(2, ws_eval.max_row + 1):
            t_name = ws_eval.cell(row=r, column=2).value
            c1 = str(ws_eval.cell(row=r, column=6).value or "").strip()
            c2 = str(ws_eval.cell(row=r, column=7).value or "").strip()
            c3 = str(ws_eval.cell(row=r, column=8).value or "").strip()
            feedback = str(ws_eval.cell(row=r, column=9).value or "").strip()

            if not t_name:
                continue

            # 完全合格（○/○/○）ではないものを対象にする
            if not (c1 == "○" and c2 == "○" and c3 == "○"):
                targets.append((s_eval, r, str(t_name).strip(), cat_name, feedback))

    print(f"\n🎯 再生成・再査読の対象: 合計 {len(targets)} 件の用語を検出しました。")
    if not targets:
        print("🎉 すべての用語が完全合格しています！")
        return

    success_count = 0

    for idx, (s_eval, r_eval, term, category, old_fb) in enumerate(targets, start=1):
        print(f"\n[{idx}/{len(targets)}] 🔄 改善生成中: 【{category}】{term}")
        if old_fb:
            print(f"  💬 前回の指摘: {old_fb[:60]}...")

        # 1. マスターExcelから公式定義を取得
        off_def = ""
        if category in wb_master.sheetnames:
            ws_m = wb_master[category]
            m_headers = [c.value for c in ws_m[1] if c.value]
            if "term_name" in m_headers:
                t_idx = m_headers.index("term_name") + 1
                off_idx = m_headers.index("kakomon_official_def") + 1 if "kakomon_official_def" in m_headers else None
                for mr in range(2, ws_m.max_row + 1):
                    if str(ws_m.cell(row=mr, column=t_idx).value or "").strip() == term:
                        if off_idx:
                            off_def = str(ws_m.cell(row=mr, column=off_idx).value or "")
                        break

        # 2. 前回の指摘を反映させた再生成
        gen_prompt = f"""あなたは基本情報技術者試験の教育プロフェッショナルです。
以下のIT用語について、初学者が直感的に理解できる「日常の比喩」と「実社会での活用例」を**完全に作り直してください**。

【対象用語】: {term}
【分野】: {category}
【公式定義】: {off_def}

⚠️【前回の査読で指摘された問題点（必ず改善してください）】:
{old_fb}

■ 絶対厳守ルール：
1. 「日常の比喩」では、IT専門用語を一切使わず、料理、学校生活、買い物、交通などの身近な生活シーンだけに例えてください。
2. 「実社会での活用例」では、架空の話ではなく「LINE」「Amazon」「銀行ATM」「Suica」など誰もが知る実在サービスでの動作例を具体的に記述してください。
3. 他の用語と取り違えず、【{term}】本来の技術概念に100%合致させてください。
"""
        try:
            res_gen = client.models.generate_content(
                model=MODEL_NAME,
                contents=gen_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RewriteResponse,
                    temperature=0.3
                )
            )
            rewritten: RewriteResponse = res_gen.parsed
            if not rewritten:
                continue

            # 3. 再生成した内容を直ちにAIで再査読
            eval_prompt = f"""以下のIT用語に対する初学者向け「日常の比喩」と「実社会での活用例」を、専門教育の観点から厳格に3軸で再審査してください。

【対象用語】: {term}
【分野】: {category}
【公式定義】: {off_def}
【生成された日常の比喩】:
{rewritten.metaphor}
【生成された実社会での活用例】:
{rewritten.practical_example}

■ 審査基準：
・【評価1】比喩の身近さ: 専門用語を使わず日常の情景に落とし込めているか（○, △, ×）
・【評価2】実用例の具体性: 身近なサービスでの利用シーンが明確か（○, △, ×）
・【評価3】技術正確性: 用語の本来の意味とズレやハルシネーションがないか（○, △, ×）
"""
            res_eval = client.models.generate_content(
                model=MODEL_NAME,
                contents=eval_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EvaluationResponse,
                    temperature=0.1
                )
            )
            evaluated: EvaluationResponse = res_eval.parsed
            if not evaluated:
                continue

            judge = f"{evaluated.eval1_metaphor}/{evaluated.eval2_practical}/{evaluated.eval3_accuracy}"
            print(f"  ✨ 再査読結果: {judge}")

            # 4. 評価シートを上書き更新
            ws_eval = wb_eval[s_eval]
            ws_eval.cell(row=r_eval, column=4, value=rewritten.metaphor)
            ws_eval.cell(row=r_eval, column=5, value=rewritten.practical_example)
            ws_eval.cell(row=r_eval, column=6, value=evaluated.eval1_metaphor)
            ws_eval.cell(row=r_eval, column=7, value=evaluated.eval2_practical)
            ws_eval.cell(row=r_eval, column=8, value=evaluated.eval3_accuracy)
            ws_eval.cell(row=r_eval, column=9, value=evaluated.feedback)

            # 5. マスターExcelも更新
            if category in wb_master.sheetnames:
                ws_m = wb_master[category]
                m_headers = [c.value for c in ws_m[1] if c.value]
                t_idx = m_headers.index("term_name") + 1
                meta_idx = m_headers.index("intuitive_def_final") + 1 if "intuitive_def_final" in m_headers else None
                prac_idx = m_headers.index("practical_example_final") + 1 if "practical_example_final" in m_headers else None

                for mr in range(2, ws_m.max_row + 1):
                    if str(ws_m.cell(row=mr, column=t_idx).value or "").strip() == term:
                        if meta_idx:
                            ws_m.cell(row=mr, column=meta_idx, value=rewritten.metaphor)
                        if prac_idx:
                            ws_m.cell(row=mr, column=prac_idx, value=rewritten.practical_example)
                        break

            # 6. DBの terms テーブルも更新
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE terms 
                    SET metaphor_def = ?, practical_ex = ? 
                    WHERE trim(term_name) = ?;
                """, (rewritten.metaphor, rewritten.practical_example, term))
                conn.commit()

            success_count += 1

            # 5件ごとに中間保存（安全策）
            if success_count % 5 == 0:
                wb_eval.save(EXCEL_EVAL)
                wb_master.save(EXCEL_MASTER)
                print("  💾 中間保存を実行しました。")

            time.sleep(0.5)

        except Exception as e:
            print(f"  ⚠️ エラー発生 ({term}): {e}")

    # 最終保存
    wb_eval.save(EXCEL_EVAL)
    wb_master.save(EXCEL_MASTER)
    if conn:
        conn.close()

    print("\n" + "=" * 60)
    print(f"🎉 不合格用語の再生成＆再査読が完了しました！（{success_count} 件更新）")
    print("=" * 60)

if __name__ == "__main__":
    run_retry()
