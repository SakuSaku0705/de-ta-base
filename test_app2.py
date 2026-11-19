import os
import json
import time
import base64
import random
import logging
import sqlite3
import datetime
import urllib.request
import urllib.error
import pandas as pd
import streamlit as st

# ---------------------------------------------------------
# 1. 基本設定・UI統一設定
# ---------------------------------------------------------
st.set_page_config(page_title="FE-AI Tutor | 事前・事後テスト", page_icon="📝", layout="wide")

st.markdown("""
<meta name="google" content="notranslate">
<style>
    html, body, [class*="css"], .stApp {
        translate: no !important;
    }
</style>
""", unsafe_allow_html=True)

DB_FILE = "fe_study.db"
LOG_FILE = "test_app.log"
TARGET_GITHUB_BRANCH = "test"  # GitHubの保存先ブランチ名

def setup_logger():
    logger = logging.getLogger("FE_TEST_LOGGER")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s]: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

logger = setup_logger()

def get_db():
    return sqlite3.connect(DB_FILE)

if not os.path.exists(DB_FILE):
    st.error("⚠️ データベース（fe_study.db）が見つかりません。")
    st.stop()

def now_jst_str():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------
# 2. GitHub（testブランチ）自動ログ追記関数
# ---------------------------------------------------------
def append_csv_to_github_branch(file_path, header_row, new_rows_list, commit_msg, branch=TARGET_GITHUB_BRANCH):
    """Streamlit Secretsを使って指定ブランチのCSVに複数行追記する"""
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        repo = st.secrets.get("GITHUB_REPO")
    except Exception:
        return

    if not token or not repo:
        return

    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    get_url = f"{api_url}?ref={branch}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FE-AI-Tutor-Test-Logger"
    }

    sha = None
    current_content = header_row

    # 1. 既存ファイルの取得（testブランチから）
    try:
        req = urllib.request.Request(get_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=8) as res:
            data = json.loads(res.read().decode("utf-8"))
            sha = data.get("sha")
            decoded = base64.b64decode(data.get("content", "")).decode("utf-8")
            current_content = decoded if decoded.endswith("\n") else decoded + "\n"
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return
    except Exception:
        return

    updated_content = current_content + "".join(new_rows_list)
    encoded_content = base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": commit_msg,
        "content": encoded_content,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    # 2. GitHubのtestブランチへ書き込み（PUT）
    try:
        put_req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT"
        )
        urllib.request.urlopen(put_req, timeout=8)
    except Exception:
        pass

# ---------------------------------------------------------
# 3. テスト用テーブルの初期化（既存テーブルへの列自動追加対応）
# ---------------------------------------------------------
def init_test_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        test_type TEXT,
        question_id INTEGER,
        term_name TEXT,
        sub_category TEXT,
        selected_choice TEXT,
        correct_ans TEXT,
        is_correct INTEGER,
        response_time_seconds REAL DEFAULT 0,
        answered_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    # 既存のtest_logsに不足している列があれば自動追加
    cur.execute("PRAGMA table_info(test_logs)")
    log_cols = [c[1] for c in cur.fetchall()]
    if "response_time_seconds" not in log_cols:
        cur.execute("ALTER TABLE test_logs ADD COLUMN response_time_seconds REAL DEFAULT 0")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        user_name TEXT,
        major_type TEXT,
        test_type TEXT,
        score INTEGER,
        total_questions INTEGER,
        accuracy_rate REAL,
        total_time_seconds REAL DEFAULT 0,
        completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, test_type)
    )
    """)
    # 既存のtest_resultsに不足している列があれば自動追加
    cur.execute("PRAGMA table_info(test_results)")
    res_cols = [c[1] for c in cur.fetchall()]
    for col_name, col_def in [
        ("user_name", "TEXT"),
        ("major_type", "TEXT"),
        ("total_time_seconds", "REAL DEFAULT 0")
    ]:
        if col_name not in res_cols:
            cur.execute(f"ALTER TABLE test_results ADD COLUMN {col_name} {col_def}")

    conn.commit()
    conn.close()
    
init_test_db()

# ---------------------------------------------------------
# 4. セッション状態の初期化
# ---------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.session_state.major_type = "情報科学科・理系"

if "test_mode" not in st.session_state:
    st.session_state.test_mode = "HOME"

if "test_questions" not in st.session_state:
    st.session_state.test_questions = []
if "test_index" not in st.session_state:
    st.session_state.test_index = 0
if "test_user_answers" not in st.session_state:
    st.session_state.test_user_answers = {}
if "current_test_type" not in st.session_state:
    st.session_state.current_test_type = ""
if "q_start_time" not in st.session_state:
    st.session_state.q_start_time = time.time()

# ---------------------------------------------------------
# 5. ログイン画面
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.markdown('<h1 translate="no">📝 基本情報技術者試験 効果検証テスト</h1>', unsafe_allow_html=True)
    st.subheader("被験者ログイン")
    
    col1, _ = st.columns([1.2, 1])
    with col1:
        input_uid = st.text_input("被験者ID（学習システムと同じID）：", placeholder="例: user01")
        input_name = st.text_input("お名前（ニックネーム可）：", placeholder="例: 奥田 さえ")
        input_major = st.radio("専攻・バックグラウンドを選択：", ["情報科学科・理系", "文系・初学者"], horizontal=True)
        
        if st.button("ログインして評価テストに進む", type="primary"):
            if input_uid.strip() and input_name.strip():
                st.session_state.logged_in = True
                st.session_state.user_id = input_uid.strip()
                st.session_state.user_name = input_name.strip()
                st.session_state.major_type = input_major
                logger.info(f"TEST_USER_LOGIN: user_id={input_uid.strip()}, major={input_major}")
                st.rerun()
            else:
                st.error("被験者IDとお名前を入力してください。")
    st.stop()

# ---------------------------------------------------------
# 6. サイドバー
# ---------------------------------------------------------
with st.sidebar:
    st.markdown(f'<div translate="no">👤 被験者: <b>{st.session_state.user_name}</b> さん<br><small>ID: {st.session_state.user_id} ｜ {st.session_state.major_type}</small></div>', unsafe_allow_html=True)
    st.markdown("---")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT test_type, score, total_questions, accuracy_rate FROM test_results WHERE user_id = ?", (st.session_state.user_id,))
    completed_tests = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}
    conn.close()

    st.subheader("📊 受験ステータス")
    pre_status = "✅ 完了" if "事前テスト" in completed_tests else "❌ 未受験"
    post_status = f"✅ 完了 ({completed_tests['事後テスト'][0]}/{completed_tests['事後テスト'][1]}問)" if "事後テスト" in completed_tests else "❌ 未受験"
    
    st.write(f"・事前テスト: {pre_status}")
    st.write(f"・事後テスト: {post_status}")

    st.markdown("---")
    if st.button("ログアウト", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.test_mode = "HOME"
        st.rerun()

# ---------------------------------------------------------
# 7. 出題ロジック（重点7分野から全被験者共通の固定10問セットを生成）
# ---------------------------------------------------------
# 重点7分野の配分（計10問：出題頻度の高いセキュリティ・ネットワーク・DBを各2問、他4分野を各1問）
FIXED_TEST_BLUEPRINT = [
    "11. セキュリティ",
    "11. セキュリティ",
    "10. ネットワーク",
    "10. ネットワーク",
    "9. データベース",
    "9. データベース",
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "12. システム開発技術",
    "22. 企業活動"
]

def get_fixed_test_questions(test_type):
    """
    全被験者で完全に同一の10問セット（事前10問 / 事後10問・重複なし）をシード固定で抽出する
    """
    conn = get_db()
    cur = conn.cursor()

    # 事前・事後で常に同じ問題セットになるよう固定シードを使用
    rng_pre = random.Random(20261119)
    rng_post = random.Random(20261120)

    # 分野ごとに利用可能な全問題をterm_name順で確定取得
    pool_by_cat = {}
    for cat in set(FIXED_TEST_BLUEPRINT):
        cur.execute("""
            SELECT rowid, term_name, sub_category, question_text, choice_a, choice_b, choice_c, choice_d, correct_ans, explanation_beginner
            FROM terms_master
            WHERE sub_category LIKE ? AND question_text IS NOT NULL AND TRIM(question_text) != ''
            ORDER BY term_name ASC
        """, (f"%{cat}%",))
        rows = cur.fetchall()
        rng_pre.shuffle(rows)
        pool_by_cat[cat] = rows

    conn.close()

    # 事前テスト10問と事後テスト10問を重複なしで切り出し
    pre_questions = []
    post_questions = []
    cat_pointer = {cat: 0 for cat in set(FIXED_TEST_BLUEPRINT)}

    for cat in FIXED_TEST_BLUEPRINT:
        idx = cat_pointer[cat]
        rows = pool_by_cat.get(cat, [])
        if idx < len(rows):
            pre_questions.append(rows[idx])
        if idx + 1 < len(rows):
            post_questions.append(rows[idx + 1])
        elif idx < len(rows):
            post_questions.append(rows[idx])
        cat_pointer[cat] += 2

    # 出題順も固定シードでシャッフル
    rng_pre.shuffle(pre_questions)
    rng_post.shuffle(post_questions)

    return pre_questions if test_type == "事前テスト" else post_questions

# ---------------------------------------------------------
# 8. メイン画面の挙動制御
# ---------------------------------------------------------

# 【ホーム画面】
if st.session_state.test_mode == "HOME":
    st.title("📝 効果測定システム（事前・事後テスト）")
    st.write("学習システムの利用効果を検証するため、学習前と学習後にそれぞれ10問のテストを行います。")
    st.info("※ 事前テストと事後テストは、重点7分野から同等難易度で選定された共通10問です。")

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. 事前テスト")
        st.write("学習システムを利用する前に受験してください（目安：7分）。")
        if "事前テスト" in completed_tests:
            st.success("✅ 事前テストは提出済みです。続いて学習システムでの学習に進んでください。")
        else:
            if st.button("🚀 事前テストを開始する", type="primary", use_container_width=True):
                st.session_state.test_questions = get_fixed_test_questions("事前テスト")
                st.session_state.test_index = 0
                st.session_state.test_user_answers = {}
                st.session_state.current_test_type = "事前テスト"
                st.session_state.test_mode = "TEST_RUN"
                st.session_state.q_start_time = time.time()
                logger.info(f"PRE_TEST_START: user_id={st.session_state.user_id}")
                st.rerun()

    with col2:
        st.subheader("2. 事後テスト")
        st.write("学習システムでの学習（25分）を終えた後に受験してください。")
        if "事後テスト" in completed_tests:
            st.success(f"✅ 受講済み（スコア: {completed_tests['事後テスト'][0]} / {completed_tests['事後テスト'][1]} 問）")
            if st.button("テスト結果・成績比較を確認する"):
                st.session_state.current_test_type = "事後テスト"
                st.session_state.test_mode = "RESULT_VIEW"
                st.rerun()
        else:
            can_start = "事前テスト" in completed_tests
            if st.button("🚀 事後テストを開始する", type="primary", use_container_width=True, disabled=not can_start):
                st.session_state.test_questions = get_fixed_test_questions("事後テスト")
                st.session_state.test_index = 0
                st.session_state.test_user_answers = {}
                st.session_state.current_test_type = "事後テスト"
                st.session_state.test_mode = "TEST_RUN"
                st.session_state.q_start_time = time.time()
                logger.info(f"POST_TEST_START: user_id={st.session_state.user_id}")
                st.rerun()
            if not can_start:
                st.caption("⚠️ 事前テスト完了後に開放されます。")

# 【テスト解答画面】
elif st.session_state.test_mode == "TEST_RUN":
    q_list = st.session_state.test_questions
    idx = st.session_state.test_index
    total = len(q_list)
    test_type = st.session_state.current_test_type

    st.markdown(f"## 📝 {test_type} （{idx + 1} / {total} 問）")
    
    if idx < total:
        q = q_list[idx]
        q_id, q_term, q_sub_cat, q_text, c_a, c_b, c_c, c_d, c_ans, exp = q

        st.progress((idx + 1) / total)
        st.caption(f"出題分野: **{q_sub_cat}**")
        st.markdown(f"### Q{idx + 1}. {q_text}")

        choices = [f"ア: {c_a}", f"イ: {c_b}", f"ウ: {c_c}", f"エ: {c_d}"]
        already_selected = st.session_state.test_user_answers.get(idx, {}).get("selected_choice", None)
        default_index = [c[0] for c in choices].index(already_selected) if already_selected else 0

        user_choice = st.radio("選択肢：", choices, index=default_index, key=f"test_radio_{idx}")
        selected_char = user_choice[0]

        col_prev, col_next = st.columns([1, 1])
        
        with col_prev:
            if idx > 0:
                if st.button("⬅️ 前の問題へ"):
                    elapsed = round(time.time() - st.session_state.q_start_time, 1)
                    prev_elapsed = st.session_state.test_user_answers.get(idx, {}).get("elapsed", 0.0)
                    st.session_state.test_user_answers[idx] = {
                        "q_id": q_id, "term": q_term, "sub_cat": q_sub_cat,
                        "selected_choice": selected_char, "correct_ans": c_ans,
                        "elapsed": round(prev_elapsed + elapsed, 1)
                    }
                    st.session_state.test_index -= 1
                    st.session_state.q_start_time = time.time()
                    st.rerun()

        with col_next:
            btn_label = "次の問題へ ➔" if (idx + 1) < total else "テストを提出する 🏁"
            if st.button(btn_label, type="primary"):
                elapsed = round(time.time() - st.session_state.q_start_time, 1)
                prev_elapsed = st.session_state.test_user_answers.get(idx, {}).get("elapsed", 0.0)
                st.session_state.test_user_answers[idx] = {
                    "q_id": q_id, "term": q_term, "sub_cat": q_sub_cat,
                    "selected_choice": selected_char, "correct_ans": c_ans,
                    "elapsed": round(prev_elapsed + elapsed, 1)
                }
                
                if (idx + 1) < total:
                    st.session_state.test_index += 1
                    st.session_state.q_start_time = time.time()
                    st.rerun()
                else:
                    # 全問回答完了 -> ローカルDB & GitHub（testブランチ）へ保存
                    conn = get_db()
                    cur = conn.cursor()
                    correct_count = 0
                    total_sec = 0.0
                    ts_now = now_jst_str()
                    detail_csv_rows = []

                    for i in sorted(st.session_state.test_user_answers.keys()):
                        a_data = st.session_state.test_user_answers[i]
                        is_corr = 1 if a_data["selected_choice"] == str(a_data["correct_ans"]).strip() else 0
                        if is_corr:
                            correct_count += 1
                        q_sec = a_data.get("elapsed", 0.0)
                        total_sec += q_sec

                        cur.execute("""
                        INSERT INTO test_logs (user_id, test_type, question_id, term_name, sub_category, selected_choice, correct_ans, is_correct, response_time_seconds, answered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (st.session_state.user_id, test_type, a_data["q_id"], a_data["term"], a_data["sub_cat"], a_data["selected_choice"], a_data["correct_ans"], is_corr, q_sec, ts_now))

                        safe_term = str(a_data["term"]).replace('"', '""')
                        safe_cat = str(a_data["sub_cat"]).replace('"', '""')
                        detail_csv_rows.append(
                            f'"{ts_now}","{st.session_state.user_id}","{st.session_state.major_type}","{test_type}",{i+1},"{safe_cat}","{safe_term}","{a_data["selected_choice"]}","{a_data["correct_ans"]}",{is_corr},{q_sec}\n'
                        )

                    acc_rate = round((correct_count / total) * 100, 1)
                    total_sec = round(total_sec, 1)

                    cur.execute("""
                    INSERT INTO test_results (user_id, user_name, major_type, test_type, score, total_questions, accuracy_rate, total_time_seconds, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, test_type) DO UPDATE SET score=?, accuracy_rate=?, total_time_seconds=?, completed_at=?
                    """, (st.session_state.user_id, st.session_state.user_name, st.session_state.major_type, test_type, correct_count, total, acc_rate, total_sec, ts_now, correct_count, acc_rate, total_sec, ts_now))
                    
                    conn.commit()
                    conn.close()

                    # 1. GitHub testブランチへサマリーCSV追記
                    sum_header = "timestamp,user_id,user_name,major_type,test_type,score,total_questions,accuracy_rate,total_time_seconds\n"
                    safe_uname = str(st.session_state.user_name).replace('"', '""')
                    sum_row = [f'"{ts_now}","{st.session_state.user_id}","{safe_uname}","{st.session_state.major_type}","{test_type}",{correct_count},{total},{acc_rate},{total_sec}\n']
                    append_csv_to_github_branch(
                        "test_results.csv", sum_header, sum_row,
                        f"test summary: {st.session_state.user_id} - {test_type} ({acc_rate}%)"
                    )

                    # 2. GitHub testブランチへ1問ごとの詳細ログCSV追記
                    det_header = "timestamp,user_id,major_type,test_type,q_num,sub_category,term_name,selected_choice,correct_ans,is_correct,response_time_seconds\n"
                    append_csv_to_github_branch(
                        "test_detail_logs.csv", det_header, detail_csv_rows,
                        f"test details: {st.session_state.user_id} - {test_type}"
                    )

                    logger.info(f"TEST_COMPLETED: user={st.session_state.user_id}, type={test_type}, score={correct_count}/{total}")
                    st.session_state.test_mode = "RESULT_VIEW"
                    st.rerun()

# 【結果表示画面】
elif st.session_state.test_mode == "RESULT_VIEW":
    test_type = st.session_state.current_test_type

    if test_type == "事前テスト":
        # 事前テスト直後は記憶バイアス防止のためスコアと正答を非表示にする
        st.title("✅ 事前テスト 提出完了")
        st.success("事前テストの回答を記録しました！ご協力ありがとうございます。")
        st.info("📌 正答率のフィードバック防⽌のため、事前テストの採点結果は**事後テスト完了後**にまとめて表示されます。\n\n続いて、学習システム「FE-AI Tutor」で25分間の学習を行ってください。")
    else:
        # 事後テスト完了後は事前・事後の比較と詳細を表示
        st.title("🏆 評価テスト 結果一覧")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT test_type, score, total_questions, accuracy_rate FROM test_results WHERE user_id = ?", (st.session_state.user_id,))
        res_map = {r[0]: r for r in cur.fetchall()}

        c1, c2 = st.columns(2)
        if "事前テスト" in res_map:
            _, s_pre, t_pre, r_pre = res_map["事前テスト"]
            c1.metric("事前テスト 正答率", f"{r_pre:.1f}%", f"{s_pre} / {t_pre} 問正解", delta_color="off")
        if "事後テスト" in res_map:
            _, s_post, t_post, r_post = res_map["事後テスト"]
            diff = round(r_post - res_map["事前テスト"][3], 1) if "事前テスト" in res_map else 0.0
            c2.metric("事後テスト 正答率", f"{r_post:.1f}%", f"{diff:+.1f}% ({s_post} / {t_post} 問正解)")

        st.markdown("---")
        st.subheader("📋 事後テスト 出題分野別の正誤一覧")
        df_logs = pd.read_sql("""
        SELECT sub_category AS 分野, term_name AS 対象用語, selected_choice AS あなたの回答, correct_ans AS 正解,
               CASE WHEN is_correct = 1 THEN '✅ 正解' ELSE '❌ 不正解' END AS 判定
        FROM test_logs
        WHERE user_id = ? AND test_type = '事後テスト'
        """, conn, params=(st.session_state.user_id,))
        st.dataframe(df_logs, use_container_width=True)
        conn.close()

    if st.button("🏠 ホームへ戻る", type="primary"):
        st.session_state.test_mode = "HOME"
        st.rerun()