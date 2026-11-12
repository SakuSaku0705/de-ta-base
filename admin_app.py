"""
FE-AI Tutor: 学習行動・研究データ分析ダッシュボード（被験者ID・滞在秒数・時系列ログ対応版）
"""

import streamlit as st
import sqlite3
import pandas as pd
import os

st.set_page_config(page_title="FE-AI Tutor 研究分析ダッシュボード", layout="wide", page_icon="📊")

st.markdown("""
<meta name="google" content="notranslate">
<style>
    html, body, [class*="css"], .stApp {
        translate: no !important;
    }
</style>
""", unsafe_allow_html=True)

DB_FILE = "fe_study.db"

if not os.path.exists(DB_FILE):
    st.error("⚠️ データベース（fe_study.db）が見つかりません。")
    st.stop()

def get_conn():
    return sqlite3.connect(DB_FILE)

conn = get_conn()

st.title("📊 FE-AI Tutor 学習行動・研究データ分析ダッシュボード")
st.caption("被験者ID別の学習時間（秒）・問題演習履歴・時系列アクションログの集計基盤")

# =========================================================
# 1. 全体サマリー指標
# =========================================================
col1, col2, col3, col4 = st.columns(4)

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

try:
    term_log_cnt = pd.read_sql("SELECT COUNT(*) FROM term_logs", conn).iloc[0, 0]
    total_study_sec = pd.read_sql("SELECT COALESCE(SUM(duration_seconds), 0) FROM term_logs", conn).iloc[0, 0]
except Exception:
    term_log_cnt = 0
    total_study_sec = 0

try:
    quiz_log_cnt = pd.read_sql("SELECT COUNT(*) FROM quiz_logs", conn).iloc[0, 0]
except Exception:
    quiz_log_cnt = 0

col1.metric("参加被験者数（ユニークID）", f"{user_cnt} 名")
col2.metric("用語閲覧回数", f"{term_log_cnt} 回")
col3.metric("総用語学習時間", f"{round(total_study_sec / 60, 1)} 分 ({round(total_study_sec, 1)}秒)")
col4.metric("総問題解答回数", f"{quiz_log_cnt} 問")

st.markdown("---")

# 被験者フィルター（全被験者 または 特定のuser_id）
user_options = ["すべての被験者"] + sorted(df_users["user_id"].tolist())
selected_user = st.selectbox("🔍 表示する被験者IDを選択:", user_options)

tab_summary, tab_timeline, tab_term, tab_quiz, tab_manage = st.tabs([
    "👤 被験者ID別 学習サマリー",
    "🕒 時系列アクションログ（何時に何をしたか）",
    "💡 用語学習ログ（滞在秒数詳細）",
    "📝 問題演習ログ（解答秒数・正誤詳細）",
    "🗑️ データ管理・CSV出力"
])

# =========================================================
# TAB 1: 被験者ID別 学習サマリー
# =========================================================
with tab_summary:
    st.subheader("👤 被験者ID別の学習時間・演習成績一覧")
    st.caption("論文の分析用に、各被験者が「何秒間用語を勉強したか」「何問解いて何％正解したか」を集計します。")

    try:
        query_summary = """
        WITH all_ids AS (
            SELECT DISTINCT user_id FROM term_logs WHERE user_id IS NOT NULL
            UNION
            SELECT DISTINCT user_id FROM quiz_logs WHERE user_id IS NOT NULL
        ),
        t_agg AS (
            SELECT 
                user_id,
                COUNT(*) AS 用語閲覧回数,
                COUNT(DISTINCT term_name) AS 学習用語数_ユニーク,
                ROUND(COALESCE(SUM(duration_seconds), 0), 1) AS 用語学習合計_秒,
                ROUND(COALESCE(AVG(duration_seconds), 0), 1) AS 用語平均滞在_秒
            FROM term_logs
            GROUP BY user_id
        ),
        q_agg AS (
            SELECT 
                user_id,
                COUNT(*) AS 問題解答数,
                SUM(COALESCE(is_correct, 0)) AS 正解数,
                ROUND(AVG(COALESCE(is_correct, 0)) * 100, 1) AS 演習正答率_パーセント,
                ROUND(COALESCE(SUM(response_time_seconds), 0), 1) AS 問題演習合計_秒,
                ROUND(COALESCE(AVG(response_time_seconds), 0), 1) AS 問題平均解答_秒
            FROM quiz_logs
            GROUP BY user_id
        )
        SELECT 
            a.user_id AS ユーザID,
            COALESCE(t.学習用語数_ユニーク, 0) AS 学習用語数,
            COALESCE(t.用語閲覧回数, 0) AS 用語閲覧回数,
            COALESCE(t.用語学習合計_秒, 0) AS 用語学習合計_秒,
            COALESCE(t.用語平均滞在_秒, 0) AS 用語平均滞在_秒,
            COALESCE(q.問題解答数, 0) AS 問題解答数,
            COALESCE(q.正解数, 0) AS 正解数,
            COALESCE(q.演習正答率_パーセント, 0) AS 演習正答率_パーセント,
            COALESCE(q.問題演習合計_秒, 0) AS 問題演習合計_秒,
            COALESCE(q.問題平均解答_秒, 0) AS 問題平均解答_秒
        FROM all_ids a
        LEFT JOIN t_agg t ON a.user_id = t.user_id
        LEFT JOIN q_agg q ON a.user_id = q.user_id
        ORDER BY a.user_id ASC
        """
        df_sum = pd.read_sql(query_summary, conn)
        if selected_user != "すべての被験者":
            df_sum = df_sum[df_sum["ユーザID"] == selected_user]

        st.dataframe(df_sum, use_container_width=True)

        csv_sum = df_sum.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 被験者ID別サマリーをCSVダウンロード",
            data=csv_sum,
            file_name="user_id_study_summary.csv",
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"サマリー集計エラー: {e}")

# =========================================================
# TAB 2: 時系列アクションログ（何時に誰が何をしたか）
# =========================================================
with tab_timeline:
    st.subheader("🕒 時系列アクションログ（誰が・何時に・何をしたか・何秒かけたか）")
    st.caption("用語学習と問題演習を時間順に並べて、学習の流れを追跡できます。")

    try:
        query_timeline = """
        SELECT 
            viewed_at AS 日時,
            user_id AS ユーザID,
            '💡 用語学習' AS アクション種別,
            term_name AS 対象用語,
            '-' AS 解答結果,
            ROUND(COALESCE(duration_seconds, 0), 1) AS 所要時間_秒
        FROM term_logs
        UNION ALL
        SELECT 
            answered_at AS 日時,
            user_id AS ユーザID,
            '📝 問題演習 (' || COALESCE(question_type, 'Q1') || ')' AS アクション種別,
            term_name AS 対象用語,
            CASE is_correct WHEN 1 THEN '✅ 正解 (' || selected_choice || ')' ELSE '❌ 不正解 (' || selected_choice || ')' END AS 解答結果,
            ROUND(COALESCE(response_time_seconds, 0), 1) AS 所要時間_秒
        FROM quiz_logs
        ORDER BY 日時 DESC
        """
        df_tl = pd.read_sql(query_timeline, conn)
        if selected_user != "すべての被験者":
            df_tl = df_tl[df_tl["ユーザID"] == selected_user]

        st.dataframe(df_tl, use_container_width=True)

        csv_tl = df_tl.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 時系列アクションログをCSVダウンロード",
            data=csv_tl,
            file_name="user_timeline_logs.csv",
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"時系列ログ取得エラー: {e}")

# =========================================================
# TAB 3: 用語学習ログ（滞在秒数詳細）
# =========================================================
with tab_term:
    st.subheader("💡 用語学習ログ（どの用語に何秒かけたか）")

    try:
        df_tlog = pd.read_sql("""
            SELECT 
                id AS ログID,
                viewed_at AS 閲覧日時,
                user_id AS ユーザID,
                term_name AS 用語名,
                ROUND(COALESCE(duration_seconds, 0), 1) AS 滞在時間_秒
            FROM term_logs
            ORDER BY viewed_at DESC
        """, conn)

        if selected_user != "すべての被験者":
            df_tlog = df_tlog[df_tlog["ユーザID"] == selected_user]

        st.dataframe(df_tlog, use_container_width=True)

        if not df_tlog.empty:
            st.markdown("##### 用語別の合計閲覧時間（秒）")
            term_chart = df_tlog.groupby("用語名")["滞在時間_秒"].sum().sort_values(ascending=False).head(20)
            st.bar_chart(term_chart)
    except Exception as e:
        st.error(f"用語ログ取得エラー: {e}")

# =========================================================
# TAB 4: 問題演習ログ（解答秒数・正誤詳細）
# =========================================================
with tab_quiz:
    st.subheader("📝 問題演習ログ（何時にどの問題を何秒で解いたか）")

    try:
        df_qlog = pd.read_sql("""
            SELECT 
                id AS ログID,
                answered_at AS 解答日時,
                user_id AS ユーザID,
                term_name AS 対象用語,
                COALESCE(question_type, 'Q1') AS 問題種別,
                selected_choice AS 選択回答,
                CASE is_correct WHEN 1 THEN '✅ 正解' ELSE '❌ 不正解' END AS 正誤,
                ROUND(COALESCE(response_time_seconds, 0), 1) AS 解答時間_秒
            FROM quiz_logs
            ORDER BY answered_at DESC
        """, conn)

        if selected_user != "すべての被験者":
            df_qlog = df_qlog[df_qlog["ユーザID"] == selected_user]

        st.dataframe(df_qlog, use_container_width=True)
    except Exception as e:
        st.error(f"問題ログ取得エラー: {e}")

# =========================================================
# TAB 5: データ管理・削除
# =========================================================
with tab_manage:
    st.subheader("🗑️ テスト用アカウント・ログデータの削除")
    st.caption("動作確認で使ったダミーID（例: test, aaa など）のログを削除して本番実験前に綺麗にします。")

    all_id_list = sorted(df_users["user_id"].tolist()) if not df_users.empty else []
    if all_id_list:
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            del_target = st.selectbox("削除するユーザIDを選択:", all_id_list)
        with col_del2:
            st.write("")
            if st.button("🗑️ このIDの全ログを削除", type="primary"):
                cur = conn.cursor()
                cur.execute("DELETE FROM term_logs WHERE user_id = ?", (del_target,))
                cur.execute("DELETE FROM quiz_logs WHERE user_id = ?", (del_target,))
                conn.commit()
                st.success(f"ユーザID `{del_target}` のログをすべて削除しました。")
                st.rerun()
    else:
        st.info("削除可能なログデータはありません。")

conn.close()