"""
【FE-AI Tutor】基本情報技術者試験 初学者向け学習支援システム
- 卒論向け高品位UI: 段階的理解モデル（概要 → 比喩 → 実用例 → 試験対策・図解）
"""

import os
import sqlite3
import streamlit as st

st.set_page_config(
    page_title="FE-AI Tutor | 基本情報技術者 学習支援",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "fe_study.db"

# カスタムCSS（見やすさと学術的な落ち着きを兼ね備えたモダンデザイン）
st.markdown("""
<style>
    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .overview-box {
        background-color: #F8FAFC;
        border-left: 5px solid #2563EB;
        padding: 1.2rem;
        border-radius: 6px;
        margin-bottom: 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .overview-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.5rem;
    }
    .overview-text {
        font-size: 1.0rem;
        line-height: 1.6;
        color: #334155;
    }
    .content-box {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1.5rem;
        margin-top: 1rem;
        line-height: 1.8;
    }
    .badge-cat {
        background-color: #EFF6FF;
        color: #1D4ED8;
        padding: 0.3rem 0.6rem;
        border-radius: 4px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

def get_db_connection():
    if not os.path.exists(DB_FILE):
        return None
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# サイドバー：ナビゲーションと用語選択
st.sidebar.title("🎓 FE-AI Tutor")
st.sidebar.caption("基本情報技術者（科目A）初学者特化システム")

conn = get_db_connection()
if not conn:
    st.error(f"データベース '{DB_FILE}' が見つかりません。'python3 sync_db.py --rebuild' を実行してください。")
    st.stop()

# 分野一覧の取得
cur = conn.cursor()
cur.execute("SELECT DISTINCT sub_category FROM terms WHERE sub_category IS NOT NULL ORDER BY sub_category;")
categories = [row["sub_category"] for row in cur.fetchall()]

selected_cat = st.sidebar.selectbox("📂 分野を選択", categories)

# 用語一覧の取得
cur.execute("SELECT term_name FROM terms WHERE sub_category = ? ORDER BY term_name;", (selected_cat,))
terms = [row["term_name"] for row in cur.fetchall()]

selected_term = st.sidebar.selectbox("🔍 学習する用語を選択", terms)

# 選択用語の全データ取得
cur.execute("SELECT * FROM terms WHERE term_name = ?;", (selected_term,))
term_data = cur.fetchone()

# =========================================================
# メイン画面表示（教育的認知ステップ順UI）
# =========================================================
if term_data:
    st.markdown(f'<div class="badge-cat">分類: {term_data["sub_category"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="main-title">{term_data["term_name"]}</div>', unsafe_allow_html=True)

    # --- Step 1: 【常時表示】用語の概要・公式定義（先生の指摘対応） ---
    official_def = term_data["official_def"]
    if not official_def or str(official_def).strip() in ["", "None", "nan"]:
        official_def = "※ 現在、公式定義データを準備中です（シラバス標準定義に準拠）。"

    st.markdown(f"""
    <div class="overview-box">
        <div class="overview-title">📌 用語の概要（基本定義）</div>
        <div class="overview-text">{official_def}</div>
    </div>
    """, unsafe_allow_html=True)

    # --- Step 2: 多面的アプローチ（直感タブUI） ---
    tab_exam, tab_meta, tab_prac, tab_diagram = st.tabs([
        "📖 試験対策（着眼点とキーワード）",
        "💡 直感理解（日常の比喩）",
        "🌍 実社会での活用例",
        "🖼️ 概念図解（インフォグラフィック）"
    ])

    with tab_exam:
        st.subheader("🎯 試験の決め手 ＆ 動作ロジック")
        exam_text = term_data["exam_point_text"]
        if exam_text and str(exam_text).strip() not in ["", "None", "nan"]:
            st.info(exam_text)
        else:
            st.warning("この用語の試験直結解説は現在生成中です。")

    with tab_meta:
        st.subheader("💡 日常の生活シーンに例えると？")
        meta_text = term_data["metaphor_def"]
        if meta_text and str(meta_text).strip() not in ["", "None", "nan"]:
            st.success(meta_text)
        else:
            st.warning("直感比喩データは準備中です。")

    with tab_prac:
        st.subheader("🌍 身近なITサービスや実社会での使われ方")
        prac_text = term_data["practical_ex"]
        if prac_text and str(prac_text).strip() not in ["", "None", "nan"]:
            st.markdown(f"""
            <div class="content-box">
                {prac_text}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("実用例データは準備中です。")

    with tab_diagram:
        st.subheader("🖼️ 16:9 構造対比インフォグラフィック")
        img_path = term_data["image_path"]
        if img_path and os.path.exists(img_path):
            st.image(img_path, use_container_width=True)
        else:
            st.info("💡 この用語の図解画像は現在生成準備中です。")

    # --- Step 3: 確認演習（Q1 / Q2） ---
    st.divider()
    st.subheader("📝 理解度チェック問題")
    
    cur.execute("SELECT * FROM terms_master WHERE term_name = ?;", (selected_term,))
    quiz_data = cur.fetchone()

    if quiz_data and quiz_data["question_text"]:
        q_tab1, q_tab2 = st.tabs(["【基本】正解を見抜く問題（Q1）", "【応用】誤りを見抜く問題（Q2）"])
        
        with q_tab1:
            st.markdown(f"**問題**: {quiz_data['question_text']}")
            ans = st.radio("選択肢を選んでください:", [
                f"ア: {quiz_data['choice_a']}",
                f"イ: {quiz_data['choice_b']}",
                f"ウ: {quiz_data['choice_c']}",
                f"エ: {quiz_data['choice_d']}"
            ], key="q1_radio")
            
            if st.button("解答を確認", key="btn_q1"):
                correct = quiz_data["correct_ans"]
                if ans.startswith(correct):
                    st.success(f"🎉 正解です！（正解記号: {correct}）")
                else:
                    st.error(f"不正解です。（正解記号: {correct}）")
                
                with st.expander("詳細解説を開く", expanded=True):
                    st.markdown("**【初学者向け解説】**")
                    st.caption(quiz_data["explanation_beginner"])
                    st.markdown("**【理系・技術的解説】**")
                    st.caption(quiz_data["explanation_advanced"])

        with q_tab2:
            if quiz_data["q2_question_text"]:
                st.markdown(f"**問題**: {quiz_data['q2_question_text']}")
                ans2 = st.radio("不適切な選択肢を選んでください:", [
                    f"ア: {quiz_data['q2_choice_a']}",
                    f"イ: {quiz_data['q2_choice_b']}",
                    f"ウ: {quiz_data['q2_choice_c']}",
                    f"エ: {quiz_data['q2_choice_d']}"
                ], key="q2_radio")
                
                if st.button("解答を確認", key="btn_q2"):
                    c2 = quiz_data["q2_correct_ans"]
                    if ans2.startswith(c2):
                        st.success(f"🎉 正解です！（不適切な記述: {c2}）")
                    else:
                        st.error(f"不正解です。（正解記号: {c2}）")
                    with st.expander("詳細解説を開く", expanded=True):
                        st.caption(quiz_data["q2_exp_beginner_final"])
            else:
                st.caption("Q2問題は準備中です。")
    else:
        st.caption("現在、この用語の演習問題は登録されていません。")

conn.close()
