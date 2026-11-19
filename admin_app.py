"""
FE-AI Tutor: 管理者用コンテンツ可視化 ＆ 研究データ分析ダッシュボード
"""

import streamlit as st
import sqlite3
import pandas as pd
import os
import re

st.set_page_config(page_title="FE-AI Tutor 管理者ダッシュボード", layout="wide", page_icon="📊")

DB_FILE = "fe_study.db"

if not os.path.exists(DB_FILE):
    st.error("⚠️ データベース（fe_study.db）が見つかりません。")
    st.stop()

def get_conn():
    return sqlite3.connect(DB_FILE)

conn = get_conn()

st.title("📊 FE-AI Tutor 管理者ダッシュボード")
st.caption("データベース登録コンテンツ（用語・問題・図解）の網羅性可視化 ＆ 実験ログ集計基盤")

# =========================================================
# 1. 全体サマリー指標（DBコンテンツ ＆ 実験ログ）
# =========================================================
col1, col2, col3, col4 = st.columns(4)

try:
    total_terms = pd.read_sql("SELECT COUNT(*) FROM terms", conn).iloc[0, 0]
except Exception:
    total_terms = 0

try:
    total_q1 = pd.read_sql("SELECT COUNT(*) FROM terms_master WHERE question_text IS NOT NULL AND TRIM(question_text) != ''", conn).iloc[0, 0]
    total_q2 = pd.read_sql("SELECT COUNT(*) FROM terms_master WHERE q2_question_text IS NOT NULL AND TRIM(q2_question_text) != ''", conn).iloc[0, 0]
except Exception:
    total_q1, total_q2 = 0, 0

try:
    df_users = pd.read_sql("""
        SELECT DISTINCT user_id FROM (
            SELECT user_id FROM term_logs
            UNION
            SELECT user_id FROM quiz_logs
        ) WHERE user_id IS NOT NULL AND user_id != ''
    """, conn)
    user_cnt = len(df_users)
except Exception:
    df_users = pd.DataFrame(columns=["user_id"])
    user_cnt = 0

col1.metric("DB登録 総用語数", f"{total_terms:,} 用語")
col2.metric("Q1問題（基本）登録数", f"{total_q1:,} 問")
col3.metric("Q2問題（応用）登録数", f"{total_q2:,} 問")
col4.metric("合計問題数（Q1+Q2）", f"{(total_q1 + total_q2):,} 問")

st.markdown("---")

tab_db, tab_summary, tab_timeline, tab_manage = st.tabs([
    "📚 DB登録コンテンツ可視化（用語・問題数）",
    "👤 被験者ID別 学習サマリー",
    "🕒 時系列アクションログ",
    "🗑️ テストデータ管理"
])

# =========================================================
# TAB 1: DB登録コンテンツの可視化（新設）
# =========================================================
with tab_db:
    st.subheader("📚 分野別 登録用語数・問題数・解説完備状況")
    st.caption("卒論（第4章）に記載する正確なデータ件数と、各分野のコンテンツ充実度を確認できます。")

    try:
        df_terms = pd.read_sql("SELECT term_name, sub_category, official_def, exam_point_text, metaphor_def, practical_ex, image_path FROM terms", conn)
        df_master = pd.read_sql("SELECT term_name, question_text, q2_question_text FROM terms_master", conn)

        df_merged = pd.merge(df_terms, df_master, on="term_name", how="left")

        def is_valid(series):
            return series.notna() & (~series.astype(str).str.strip().isin(["", "None", "nan"]))

        df_merged["公式定義あり"] = is_valid(df_merged["official_def"]).astype(int)
        df_merged["試験対策あり"] = is_valid(df_merged["exam_point_text"]).astype(int)
        df_merged["日常比喩あり"] = is_valid(df_merged["metaphor_def"]).astype(int)
        df_merged["実社会例あり"] = is_valid(df_merged["practical_ex"]).astype(int)
        df_merged["図解パスあり"] = is_valid(df_merged["image_path"]).astype(int)
        df_merged["Q1問題あり"] = is_valid(df_merged["question_text"]).astype(int)
        df_merged["Q2問題あり"] = is_valid(df_merged["q2_question_text"]).astype(int)

        summary_by_cat = df_merged.groupby("sub_category", as_index=False).agg(
            登録用語数=("term_name", "count"),
            公式定義=("公式定義あり", "sum"),
            試験対策=("試験対策あり", "sum"),
            日常比喩=("日常比喩あり", "sum"),
            実社会例=("実社会例あり", "sum"),
            図解数=("図解パスあり", "sum"),
            Q1問題数=("Q1問題あり", "sum"),
            Q2問題数=("Q2問題あり", "sum")
        )

        # 分野番号順にソート
        def extract_num(cat_str):
            m = re.match(r"^(\d+)", str(cat_str))
            return int(m.group(1)) if m else 999

        summary_by_cat["sort_key"] = summary_by_cat["sub_category"].apply(extract_num)
        summary_by_cat = summary_by_cat.sort_values("sort_key").drop(columns=["sort_key"])
        summary_by_cat.rename(columns={"sub_category": "分野名"}, inplace=True)

        st.dataframe(summary_by_cat, use_container_width=True, hide_index=True)

        st.markdown("##### 📊 分野別の登録用語数 ＆ 問題数分布")
        chart_df = summary_by_cat.set_index("分野名")[["登録用語数", "Q1問題数", "Q2問題数"]]
        st.bar_chart(chart_df)

        st.markdown("##### 🔍 用語・問題データのプレビュー検索")
        kw = st.text_input("DB内の用語を検索して登録内容を確認:", placeholder="例: ファイアウォール, 正規化...")
        if kw.strip():
            filtered = df_merged[df_merged["term_name"].str.contains(kw.strip(), na=False)]
            st.dataframe(filtered[["term_name", "sub_category", "official_def", "question_text", "q2_question_text"]], use_container_width=True)

    except Exception as e:
        st.error(f"DB可視化エラー: {e}")

# =========================================================
# TAB 2: 被験者ID別 学習サマリー
# =========================================================
with tab_summary:
    st.subheader("👤 被験者ID別の学習時間・演習成績一覧")
    try:
        query_summary = """
        WITH all_ids AS (
            SELECT DISTINCT user_id FROM term_logs WHERE user_id IS NOT NULL
            UNION
            SELECT DISTINCT user_id FROM quiz_logs WHERE user_id IS NOT NULL
        ),
        t_agg AS (
            SELECT user_id, COUNT(*) AS 用語閲覧回数, COUNT(DISTINCT term_name) AS 学習用語数,
                   ROUND(COALESCE(SUM(duration_seconds), 0), 1) AS 用語学習合計_秒
            FROM term_logs GROUP BY user_id
        ),
        q_agg AS (
            SELECT user_id, COUNT(*) AS 問題解答数, SUM(COALESCE(is_correct, 0)) AS 正解数,
                   ROUND(AVG(COALESCE(is_correct, 0)) * 100, 1) AS 正答率_パーセント,
                   ROUND(COALESCE(SUM(response_time_seconds), 0), 1) AS 問題演習合計_秒
            FROM quiz_logs GROUP BY user_id
        )
        SELECT a.user_id AS ユーザID, COALESCE(t.学習用語数, 0) AS 学習用語数,
               COALESCE(t.用語閲覧回数, 0) AS 用語閲覧回数, COALESCE(t.用語学習合計_秒, 0) AS 用語学習合計_秒,
               COALESCE(q.問題解答数, 0) AS 問題解答数, COALESCE(q.正解数, 0) AS 正解数,
               COALESCE(q.正答率_パーセント, 0) AS 正答率_パーセント, COALESCE(q.問題演習合計_秒, 0) AS 問題演習合計_秒
        FROM all_ids a LEFT JOIN t_agg t ON a.user_id = t.user_id LEFT JOIN q_agg q ON a.user_id = q.user_id
        ORDER BY a.user_id ASC
        """
        df_sum = pd.read_sql(query_summary, conn)
        st.dataframe(df_sum, use_container_width=True)
    except Exception as e:
        st.error(f"サマリー集計エラー: {e}")

# =========================================================
# TAB 3: 時系列アクションログ
# =========================================================
with tab_timeline:
    st.subheader("🕒 時系列アクションログ")
    try:
        query_timeline = """
        SELECT viewed_at AS 日時, user_id AS ユーザID, '💡 用語学習' AS アクション種別,
               term_name AS 対象用語, '-' AS 解答結果, ROUND(COALESCE(duration_seconds, 0), 1) AS 所要時間_秒
        FROM term_logs
        UNION ALL
        SELECT answered_at AS 日時, user_id AS ユーザID, '📝 問題演習 (' || COALESCE(question_type, 'Q1') || ')' AS アクション種別,
               term_name AS 対象用語,
               CASE is_correct WHEN 1 THEN '✅ 正解 (' || selected_choice || ')' ELSE '❌ 不正解 (' || selected_choice || ')' END AS 解答結果,
               ROUND(COALESCE(response_time_seconds, 0), 1) AS 所要時間_秒
        FROM quiz_logs
        ORDER BY 日時 DESC
        """
        df_tl = pd.read_sql(query_timeline, conn)
        st.dataframe(df_tl, use_container_width=True)
    except Exception as e:
        st.error(f"時系列ログ取得エラー: {e}")

# =========================================================
# TAB 4: データ管理・削除
# =========================================================
with tab_manage:
    st.subheader("🗑️ テスト用アカウント・ログデータの削除")
    all_id_list = sorted(df_users["user_id"].tolist()) if not df_users.empty else []
    if all_id_list:
        del_target = st.selectbox("削除するユーザIDを選択:", all_id_list)
        if st.button("🗑️ このIDの全ログを削除", type="primary"):
            cur = conn.cursor()
            cur.execute("DELETE FROM term_logs WHERE user_id = ?", (del_target,))
            cur.execute("DELETE FROM quiz_logs WHERE user_id = ?", (del_target,))
            conn.commit()
            st.success(f"ユーザID `{del_target}` のログを削除しました。")
            st.rerun()
    else:
        st.info("削除可能なローカルログデータはありません。")

conn.close()