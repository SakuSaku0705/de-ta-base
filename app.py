"""
【FE-AI Tutor】基本情報技術者試験 初学者向け学習支援システム
- UI設計: 視認性重視の縦フロー構造
  1. 用語概要（基本定義）
  2. 構造対比インフォグラフィック（常時・大画面表示）
  3. 多面的深掘りタブ（試験対策 / 直感比喩 / 実社会例）
"""

import os
import re
import sqlite3
import datetime
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="FE-AI Tutor | 基本情報技術者 学習支援",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "fe_study.db"

TARGET_7_CATEGORIES = [
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動"
]

st.markdown("""
<style>
    .main-title { font-size: 2.1rem; font-weight: 800; color: #1E3A8A; margin-bottom: 0.2rem; }
    .badge-cat { background-color: #EFF6FF; color: #1D4ED8; padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.85rem; font-weight: 600; display: inline-block; margin-bottom: 0.6rem; }
    .badge-target { background-color: #FEF3C7; color: #92400E; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 700; margin-left: 0.5rem; }
    .overview-box { background-color: #F8FAFC; border-left: 5px solid #2563EB; padding: 1.2rem; border-radius: 6px; margin-bottom: 1.4rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .overview-title { font-size: 1.05rem; font-weight: 700; color: #1E293B; margin-bottom: 0.4rem; }
    .overview-text { font-size: 0.98rem; line-height: 1.6; color: #334155; }
    .diagram-container { margin-bottom: 1.5rem; background-color: #FFFFFF; padding: 0.8rem; border-radius: 8px; border: 1px solid #E2E8F0; }
    .content-box { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 1.2rem; line-height: 1.8; }
</style>
""", unsafe_allow_html=True)

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_log_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quiz_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        term_name TEXT,
        question_type TEXT,
        selected_choice TEXT,
        is_correct INTEGER,
        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("PRAGMA table_info(quiz_logs);")
    cols = [c[1] for c in cur.fetchall()]
    if "question_type" not in cols:
        cur.execute("ALTER TABLE quiz_logs ADD COLUMN question_type TEXT DEFAULT 'Q1';")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS term_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        term_name TEXT,
        viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    conn.close()

init_log_tables()

# =========================================================
# 1. ログイン画面
# =========================================================
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None

if not st.session_state["user_id"]:
    st.title("🎓 FE-AI Tutor ログイン")
    st.caption("基本情報技術者試験（科目A）初学者特化型 学習支援システム")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 被験者ログイン")
        user_input = st.text_input("被験者IDを入力してください:", placeholder="例: student01, user_A")
        if st.button("学習を開始する", type="primary"):
            if user_input.strip():
                st.session_state["user_id"] = user_input.strip()
                st.rerun()
            else:
                st.warning("IDを入力してください。")
    with col2:
        st.info("""
        **【本システムの学習アプローチ（被験者ガイダンス）】**
        - **用語概要の把握**: シラバス公式定義に基づく基礎知識の定着
        - **視覚的構造理解**: 概念の動作や対比を大判インフォグラフィックで直感把握
        - **多面的解釈の深掘り**: 試験着眼点・日常比喩・実用例による理解の多角化
        - **二層解説問題演習**: 初学者向け直感解説と技術的詳細解説による理解度測定
        """)
    st.stop()

# =========================================================
# 2. サイドバー
# =========================================================
st.sidebar.markdown(f"👤 **ログイン中:** `{st.session_state['user_id']}`")
if st.sidebar.button("ログアウト"):
    st.session_state["user_id"] = None
    st.rerun()

st.sidebar.divider()
mode = st.sidebar.radio("📚 モードを選択", ["💡 用語学習", "📝 問題演習", "📊 学習履歴・分析"])

conn = get_db()
cur = conn.cursor()

def sort_categories(cat_list):
    def get_num(cat_str):
        m = re.match(r"^(\d+)", cat_str)
        return int(m.group(1)) if m else 999
    return sorted(cat_list, key=get_num)

# =========================================================
# 3. モード別画面
# =========================================================

# ---------------------------------------------------------
# A. 用語学習モード（縦フロー構造）
# ---------------------------------------------------------
if mode == "💡 用語学習":
    st.sidebar.subheader("🔍 用語を探す")
    
    search_keyword = st.sidebar.text_input("用語名で検索 (部分一致):", placeholder="例: TCP, 暗号化, DNS...")
    selected_term = None

    if search_keyword.strip():
        keyword_param = f"%{search_keyword.strip()}%"
        cur.execute("""
            SELECT term_name, sub_category 
            FROM terms 
            WHERE term_name LIKE ? OR official_def LIKE ?
            ORDER BY term_name;
        """, (keyword_param, keyword_param))
        search_results = cur.fetchall()

        if search_results:
            result_options = {f"{r['term_name']} （{r['sub_category']}）": r['term_name'] for r in search_results}
            selected_display = st.sidebar.selectbox(f"検索結果 ({len(search_results)}件):", list(result_options.keys()))
            selected_term = result_options[selected_display]
        else:
            st.sidebar.warning(f"「{search_keyword}」に一致する用語は見つかりませんでした。")
    else:
        cur.execute("SELECT DISTINCT sub_category FROM terms WHERE sub_category IS NOT NULL;")
        raw_cats = [row["sub_category"] for row in cur.fetchall()]
        sorted_cats = sort_categories(raw_cats)

        cat_display_map = {}
        for c in sorted_cats:
            if any(t_cat in c for t_cat in TARGET_7_CATEGORIES):
                display_label = f"🚩 {c}"
            else:
                display_label = f"    {c}  (対象外)"
            cat_display_map[display_label] = c

        selected_label = st.sidebar.selectbox("📂 分野を選択 (1〜23)", list(cat_display_map.keys()))
        selected_cat = cat_display_map[selected_label]

        cur.execute("SELECT term_name FROM terms WHERE sub_category = ? ORDER BY term_name;", (selected_cat,))
        terms = [row["term_name"] for row in cur.fetchall()]
        selected_term = st.sidebar.selectbox("🔍 用語を選択", terms)

    if selected_term:
        cur.execute("SELECT * FROM terms WHERE term_name = ?;", (selected_term,))
        tdata = cur.fetchone()

        if tdata:
            cur.execute("INSERT INTO term_logs (user_id, term_name) VALUES (?, ?);", (st.session_state["user_id"], selected_term))
            conn.commit()

            is_target_7 = any(tc in str(tdata["sub_category"]) for tc in TARGET_7_CATEGORIES)
            
            badge_html = f'<div class="badge-cat">分類: {tdata["sub_category"]}</div>'
            if is_target_7:
                badge_html += '<span class="badge-target">★ 本研究 重点対象分野</span>'
            st.markdown(badge_html, unsafe_allow_html=True)
            st.markdown(f'<div class="main-title">{tdata["term_name"]}</div>', unsafe_allow_html=True)

            if not is_target_7:
                st.caption("ℹ️ この用語は本研究の選定7分野以外の項目です。用語概要や基本演習のみご利用いただけます。")

            # ① 用語概要（最上部に常時固定表示）
            off_def = tdata["official_def"]
            if not off_def or str(off_def).strip() in ["", "None", "nan"]:
                off_def = "※ 公式定義データを読み込み中（シラバス標準定義に準拠）。"

            st.markdown(f"""
            <div class="overview-box">
                <div class="overview-title">📌 用語の概要（基本定義）</div>
                <div class="overview-text">{off_def}</div>
            </div>
            """, unsafe_allow_html=True)

            # ② 構造対比インフォグラフィック（概要の直下に大判・常時表示）
            img_path = tdata["image_path"]
            if img_path and os.path.exists(img_path):
                st.markdown(f"##### 🖼️ 構造対比インフォグラフィック")
                st.image(img_path, caption=f"【概念図解】{tdata['term_name']}", use_container_width=True)
                st.write("") # スペース空け

            # ③ 多面的アプローチ（3つの深掘りタブ）
            t_exam, t_meta, t_prac = st.tabs([
                "📖 試験対策（着眼点とキーワード）",
                "💡 直感理解（日常の比喩）",
                "🌍 実社会での活用例"
            ])

            with t_exam:
                st.subheader("🎯 試験の決め手 ＆ 動作ロジック")
                exam_text = tdata["exam_point_text"]
                if exam_text and str(exam_text).strip() not in ["", "None", "nan"]:
                    st.info(exam_text)
                else:
                    st.warning("試験直結解説テキストは準備中です。")

            with t_meta:
                st.subheader("💡 日常の生活シーンに例えると？")
                meta_text = tdata["metaphor_def"]
                if meta_text and str(meta_text).strip() not in ["", "None", "nan"]:
                    st.success(meta_text)
                else:
                    st.warning("比喩解説は準備中です。")

            with t_prac:
                st.subheader("🌍 身近なITサービスや実社会での使われ方")
                prac_text = tdata["practical_ex"]
                if prac_text and str(prac_text).strip() not in ["", "None", "nan"]:
                    st.markdown(f'<div class="content-box">{prac_text}</div>', unsafe_allow_html=True)
                else:
                    st.warning("実用例は準備中です。")

# ---------------------------------------------------------
# B. 問題演習モード
# ---------------------------------------------------------
elif mode == "📝 問題演習":
    st.title("📝 基本情報技術者（科目A）問題演習")
    st.caption("用語学習で身につけた知識を、実践的な4択問題でテストします。")

    cur.execute("SELECT DISTINCT sub_category FROM terms_master WHERE question_text IS NOT NULL;")
    raw_q_cats = [r["sub_category"] for r in cur.fetchall()]
    sorted_q_cats = sort_categories(raw_q_cats)

    col_q1, col_q2 = st.columns([1, 2])
    with col_q1:
        q_options = ["全分野ランダム"]
        q_map = {"全分野ランダム": "全分野ランダム"}
        for qc in sorted_q_cats:
            label = f"✨ {qc}" if any(tc in qc for tc in TARGET_7_CATEGORIES) else f"   {qc}"
            q_options.append(label)
            q_map[label] = qc

        sel_q_label = st.selectbox("分野を選択", q_options)
        sel_q_cat = q_map[sel_q_label]
        q_type = st.radio("問題タイプ", ["【基本】正解を見抜く問題 (Q1)", "【応用】誤りを見抜く問題 (Q2)"])

    if sel_q_cat == "全分野ランダム":
        cur.execute("SELECT * FROM terms_master WHERE question_text IS NOT NULL ORDER BY RANDOM() LIMIT 1;")
    else:
        cur.execute("SELECT * FROM terms_master WHERE sub_category = ? AND question_text IS NOT NULL ORDER BY RANDOM() LIMIT 1;", (sel_q_cat,))

    q_data = cur.fetchone()

    with col_q2:
        if q_data:
            st.markdown(f"**対象用語**: `{q_data['term_name']}` （分野: {q_data['sub_category']}）")

            if "Q1" in q_type:
                st.markdown(f"#### 問題\n{q_data['question_text']}")
                choices = [
                    f"ア: {q_data['choice_a']}",
                    f"イ: {q_data['choice_b']}",
                    f"ウ: {q_data['choice_c']}",
                    f"エ: {q_data['choice_d']}"
                ]
                ans = st.radio("あなたの回答:", choices, key=f"q1_{q_data['term_name']}")

                if st.button("解答を送信", type="primary", key="btn_submit_q1"):
                    correct = q_data["correct_ans"]
                    is_corr = 1 if ans.startswith(correct) else 0

                    cur.execute("""
                        INSERT INTO quiz_logs (user_id, term_name, question_type, selected_choice, is_correct)
                        VALUES (?, ?, 'Q1', ?, ?);
                    """, (st.session_state["user_id"], q_data["term_name"], ans[:1], is_corr))
                    conn.commit()

                    if is_corr:
                        st.success(f"🎉 正解です！（正解: {correct}）")
                    else:
                        st.error(f"不正解です。（正解: {correct}）")

                    with st.expander("💡 初学者向け分かりやすい解説", expanded=True):
                        st.write(q_data["explanation_beginner"])
                    with st.expander("🔬 理系・技術的詳細解説"):
                        st.write(q_data["explanation_advanced"])

            else:
                if q_data["q2_question_text"]:
                    st.markdown(f"#### 問題（不適切なものを選択）\n{q_data['q2_question_text']}")
                    choices2 = [
                        f"ア: {q_data['q2_choice_a']}",
                        f"イ: {q_data['q2_choice_b']}",
                        f"ウ: {q_data['q2_choice_c']}",
                        f"エ: {q_data['q2_choice_d']}"
                    ]
                    ans2 = st.radio("あなたの回答:", choices2, key=f"q2_{q_data['term_name']}")

                    if st.button("解答を送信", type="primary", key="btn_submit_q2"):
                        correct2 = q_data["q2_correct_ans"]
                        is_corr2 = 1 if ans2.startswith(correct2) else 0

                        cur.execute("""
                            INSERT INTO quiz_logs (user_id, term_name, question_type, selected_choice, is_correct)
                            VALUES (?, ?, 'Q2', ?, ?);
                        """, (st.session_state["user_id"], q_data["term_name"], ans2[:1], is_corr2))
                        conn.commit()

                        if is_corr2:
                            st.success(f"🎉 正解です！（不適切な選択肢: {correct2}）")
                        else:
                            st.error(f"不正解です。（正解: {correct2}）")

                        with st.expander("解説を確認する", expanded=True):
                            st.write(q_data["q2_exp_beginner_final"])
                else:
                    st.info("この用語のQ2問題は準備中です。")

# ---------------------------------------------------------
# C. 学習履歴・分析ダッシュボード
# ---------------------------------------------------------
elif mode == "📊 学習履歴・分析":
    st.title(f"📊 学習履歴: {st.session_state['user_id']}")

    cur.execute("SELECT * FROM quiz_logs WHERE user_id = ? ORDER BY answered_at DESC;", (st.session_state["user_id"],))
    logs = cur.fetchall()

    if logs:
        df_logs = pd.DataFrame([dict(r) for r in logs])
        total_q = len(df_logs)
        correct_q = df_logs["is_correct"].sum()
        acc = (correct_q / total_q) * 100 if total_q > 0 else 0

        m1, m2, m3 = st.columns(3)
        m1.metric("総回答数", f"{total_q} 問")
        m2.metric("正解数", f"{correct_q} 問")
        m3.metric("正答率", f"{acc:.1f} %")

        if "question_type" not in df_logs.columns:
            df_logs["question_type"] = "Q1"
        else:
            df_logs["question_type"] = df_logs["question_type"].fillna("Q1")

        show_cols = ["term_name", "question_type", "selected_choice", "is_correct", "answered_at"]
        available_cols = [c for c in show_cols if c in df_logs.columns]

        st.subheader("直近の回答履歴")
        st.dataframe(df_logs[available_cols], use_container_width=True)
    else:
        st.info("まだ演習履歴がありません。『📝 問題演習』から問題を解いてみましょう！")

conn.close()
