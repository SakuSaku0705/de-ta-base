import os
import json
import time
import random
import base64
import logging
import datetime
import sqlite3
import urllib.request
import urllib.error
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
TEST_LIMIT_SECONDS = 7 * 60  # 制限時間：7分（420秒）

# 重点7分野からの出題内訳（合計10問）
CATEGORY_QUOTAS = [
    ("11. セキュリティ", 2),
    ("10. ネットワーク", 2),
    ("9. データベース", 2),
    ("3. コンピュータ構成要素", 1),
    ("5. ソフトウェア", 1),
    ("12. システム開発技術", 1),
    ("22. 企業活動", 1),
]

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
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def now_jst_str():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------
# GitHub 自動バックアップ関数（testブランチへ保存）
# ---------------------------------------------------------
def append_test_result_to_github(ts, user_id, user_name, major_type, test_type, score, total, acc_rate, elapsed_sec):
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        repo = st.secrets.get("GITHUB_REPO")
        branch = st.secrets.get("TEST_BRANCH", "test")
        file_path = st.secrets.get("TEST_RESULT_PATH", "test_results.csv")
    except Exception:
        return

    if not token or not repo:
        return

    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}?ref={branch}"
    put_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FE-AI-Tutor-TestLogger"
    }

    safe_name = str(user_name).replace('"', '""')
    new_row = f'"{ts}","{user_id}","{safe_name}","{major_type}","{test_type}",{score},{total},{acc_rate:.1f},{elapsed_sec}\n'
    header_row = "timestamp,user_id,user_name,major_type,test_type,score,total_questions,accuracy_rate,elapsed_seconds\n"

    sha = None
    current_content = header_row

    try:
        req = urllib.request.Request(api_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode("utf-8"))
            sha = data.get("sha")
            decoded = base64.b64decode(data.get("content", "")).decode("utf-8")
            current_content = decoded if decoded.endswith("\n") else decoded + "\n"
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return
    except Exception:
        return

    updated_content = current_content + new_row
    encoded_content = base64.b64encode(updated_content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"test: {user_id} ({test_type}) {score}/{total}",
        "content": encoded_content,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    try:
        put_req = urllib.request.Request(
            put_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT"
        )
        urllib.request.urlopen(put_req, timeout=5)
    except Exception:
        pass

# ---------------------------------------------------------
# 2. ログ用テーブルの初期化（既存のterms_masterは破壊しない）
# ---------------------------------------------------------
@st.cache_resource
def init_log_tables():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        user_name TEXT,
        last_login DATETIME
    )
    """)

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
        answered_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        test_type TEXT,
        score INTEGER,
        total_questions INTEGER,
        accuracy_rate REAL,
        completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, test_type)
    )
    """)

    conn.commit()
    conn.close()

init_log_tables()

# ---------------------------------------------------------
# 3. セッション状態の初期化
# ---------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = ""
    st.session_state.user_name = ""
    st.session_state.major_type = "文系・初学者"

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
if "start_time" not in st.session_state:
    st.session_state.start_time = None

# ---------------------------------------------------------
# 4. ログイン画面
# ---------------------------------------------------------
if not st.session_state.logged_in:
    st.markdown('<h1 translate="no">📝 基本情報技術者試験 効果検証システム</h1>', unsafe_allow_html=True)
    st.subheader("被験者ログイン")
    
    col1, _ = st.columns([1.2, 1])
    with col1:
        input_uid = st.text_input("学籍番号 または 被験者ID：", placeholder="例: G23937")
        input_name = st.text_input("お名前：", placeholder="例: 奥田 さえ")
        input_major = st.radio("専攻・バックグラウンドを選択：", ["文系・初学者", "情報科学科・理系"], horizontal=True)
        
        if st.button("ログインして評価テストに進む", type="primary"):
            if input_uid.strip() and input_name.strip():
                conn = get_db()
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO users (user_id, user_name, last_login) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET last_login=CURRENT_TIMESTAMP, user_name=?
                """, (input_uid.strip(), input_name.strip(), input_name.strip()))
                conn.commit()
                conn.close()
                
                st.session_state.logged_in = True
                st.session_state.user_id = input_uid.strip()
                st.session_state.user_name = input_name.strip()
                st.session_state.major_type = input_major
                
                logger.info(f"TEST_USER_LOGIN: user_id={input_uid.strip()}, major={input_major}")
                st.rerun()
            else:
                st.error("学籍番号とお名前を入力してください。")
    st.stop()

# ---------------------------------------------------------
# 5. サイドバー（正答率は一切表示しない）
# ---------------------------------------------------------
with st.sidebar:
    st.markdown(f'<div translate="no">👤 被験者: <b>{st.session_state.user_name}</b> さん<br><small>ID: {st.session_state.user_id} ｜ {st.session_state.major_type}</small></div>', unsafe_allow_html=True)
    st.markdown("---")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT test_type FROM test_results WHERE user_id = ?", (st.session_state.user_id,))
    completed_set = {row["test_type"] for row in cur.fetchall()}
    conn.close()

    st.subheader("📊 受験ステータス")
    pre_status = "✅ 提出完了" if "事前テスト" in completed_set else "⬜ 未受験"
    post_status = "✅ 提出完了" if "事後テスト" in completed_set else "⬜ 未受験"
    
    st.write(f"・事前テスト: {pre_status}")
    st.write(f"・事後テスト: {post_status}")

    st.markdown("---")
    if st.button("ログアウト", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.test_mode = "HOME"
        st.rerun()

# ---------------------------------------------------------
# 6. AI生成問題（terms_master）からのランダム出題ロジック
# ---------------------------------------------------------
def generate_test_questions(test_type, user_id):
    """terms_masterから重点7分野のAI生成問題（Q1・Q2ミックス）を計10問ランダム抽出する"""
    conn = get_db()
    cur = conn.cursor()

    # 事後テストの場合は、すでに事前テストで出題された用語を除外する
    excluded_terms = set()
    if test_type == "事後テスト":
        cur.execute("SELECT DISTINCT term_name FROM test_logs WHERE user_id = ? AND test_type = '事前テスト'", (user_id,))
        excluded_terms = {r["term_name"] for r in cur.fetchall()}

    selected_questions = []

    for cat_name, quota in CATEGORY_QUOTAS:
        cur.execute("""
            SELECT rowid, term_name, sub_category,
                   question_text, choice_a, choice_b, choice_c, choice_d, correct_ans,
                   q2_question_text, q2_choice_a, q2_choice_b, q2_choice_c, q2_choice_d, q2_correct_ans
            FROM terms_master
            WHERE sub_category LIKE ?
              AND question_text IS NOT NULL AND TRIM(question_text) != ''
        """, (f"%{cat_name}%",))
        rows = [dict(r) for r in cur.fetchall()]

        # 除外用語を除いた候補リスト
        candidates = [r for r in rows if r["term_name"] not in excluded_terms]
        if len(candidates) < quota:
            candidates = rows

        random.shuffle(candidates)
        picked = candidates[:quota]

        for r in picked:
            has_q2 = r.get("q2_question_text") and str(r["q2_question_text"]).strip() not in ["", "None", "nan"]
            use_q2 = random.choice([True, False]) if has_q2 else False

            if use_q2:
                q_tuple = (
                    r["rowid"], r["term_name"], r["sub_category"],
                    r["q2_question_text"], r["q2_choice_a"], r["q2_choice_b"], r["q2_choice_c"], r["q2_choice_d"],
                    r["q2_correct_ans"], "Q2"
                )
            else:
                q_tuple = (
                    r["rowid"], r["term_name"], r["sub_category"],
                    r["question_text"], r["choice_a"], r["choice_b"], r["choice_c"], r["choice_d"],
                    r["correct_ans"], "Q1"
                )
            selected_questions.append(q_tuple)

    conn.close()
    random.shuffle(selected_questions)
    return selected_questions

def save_and_submit_test(test_type, total):
    """解答結果を内部DBとGitHubへ保存し、完了画面へ遷移する（被験者にはスコア非表示）"""
    conn = get_db()
    cur = conn.cursor()
    correct_count = 0
    elapsed_sec = round(time.time() - (st.session_state.start_time or time.time()), 1)
    ts = now_jst_str()

    # 同一テストの再保存時は古い明細ログを消して最新を上書き
    cur.execute("DELETE FROM test_logs WHERE user_id = ? AND test_type = ?", (st.session_state.user_id, test_type))

    q_list = st.session_state.test_questions
    for i, q in enumerate(q_list):
        q_id, q_term, q_sub_cat, q_text, c_a, c_b, c_c, c_d, c_ans, q_kind = q
        a_data = st.session_state.test_user_answers.get(i, {})
        selected_choice = a_data.get("selected_choice", "未解答")

        is_corr = 1 if selected_choice == str(c_ans).strip() else 0
        if is_corr:
            correct_count += 1

        cur.execute("""
        INSERT INTO test_logs (user_id, test_type, question_id, term_name, sub_category, selected_choice, correct_ans, is_correct, answered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (st.session_state.user_id, test_type, q_id, f"{q_term}({q_kind})", q_sub_cat, selected_choice, c_ans, is_corr, ts))

    acc_rate = (correct_count / total) * 100 if total > 0 else 0.0
    cur.execute("""
    INSERT INTO test_results (user_id, test_type, score, total_questions, accuracy_rate, completed_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id, test_type) DO UPDATE SET score=?, total_questions=?, accuracy_rate=?, completed_at=?
    """, (st.session_state.user_id, test_type, correct_count, total, acc_rate, ts, correct_count, total, acc_rate, ts))

    conn.commit()
    conn.close()

    append_test_result_to_github(
        ts, st.session_state.user_id, st.session_state.user_name,
        st.session_state.major_type, test_type, correct_count, total, acc_rate, elapsed_sec
    )

    logger.info(f"TEST_COMPLETED: user={st.session_state.user_id}, type={test_type}, score={correct_count}/{total}")
    st.session_state.test_mode = "RESULT_VIEW"

def render_javascript_timer(start_timestamp, limit_seconds):
    timer_html = f"""
    <div id="timer-box" style="text-align: right; font-size: 22px; font-weight: bold; color: darkorange; font-family: sans-serif;">
        ⏳ 残り時間: <span id="timer-text">--:--</span>
    </div>
    <script>
        const startTime = {start_timestamp};
        const limitSeconds = {limit_seconds};
        function updateTimer() {{
            const now = Math.floor(Date.now() / 1000);
            const elapsed = now - startTime;
            const remaining = Math.max(0, limitSeconds - elapsed);
            const mins = String(Math.floor(remaining / 60)).padStart(2, '0');
            const secs = String(remaining % 60).padStart(2, '0');
            const timerElem = document.getElementById("timer-text");
            const boxElem = document.getElementById("timer-box");
            if (timerElem) {{
                timerElem.innerText = mins + ":" + secs;
                if (remaining < 60) {{
                    boxElem.style.color = "red";
                }}
            }}
        }}
        updateTimer();
        setInterval(updateTimer, 1000);
    </script>
    """
    components.html(timer_html, height=45)

# ---------------------------------------------------------
# 7. メイン画面の挙動制御
# ---------------------------------------------------------

# 【1. ホーム画面】
if st.session_state.test_mode == "HOME":
    st.title("📝 効果測定システム（事前・事後テスト）")
    st.write("学習システムの利用効果を検証するため、学習前と学習後にそれぞれ10問のテストを行います。")
    st.warning("⏱️ **制限時間: 各テスト 7分（420秒）**")
    st.info("※ 公平な検証のため、テスト完了直後は正答・スコアを表示しません。実験終了後にまとめてご案内します。")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. 事前テスト")
        st.write("学習システムを利用する前に受験してください。")
        if "事前テスト" in completed_set:
            st.success("✅ 事前テストは提出完了しています。")
        else:
            if st.button("🚀 事前テストを開始する", type="primary", use_container_width=True):
                qs = generate_test_questions("事前テスト", st.session_state.user_id)
                if not qs:
                    st.error("問題データの読み込みに失敗しました。データベースを確認してください。")
                else:
                    st.session_state.test_questions = qs
                    st.session_state.test_index = 0
                    st.session_state.test_user_answers = {}
                    st.session_state.current_test_type = "事前テスト"
                    st.session_state.start_time = time.time()
                    st.session_state.test_mode = "TEST_RUN"
                    logger.info(f"PRE_TEST_START: user_id={st.session_state.user_id}")
                    st.rerun()

    with col2:
        st.subheader("2. 事後テスト")
        st.write("学習システムでの学習を終えた後に受験してください。")
        if "事後テスト" in completed_set:
            st.success("✅ 事後テストは提出完了しています。")
        else:
            can_start = "事前テスト" in completed_set
            if st.button("🚀 事後テストを開始する", type="primary", use_container_width=True, disabled=not can_start):
                qs = generate_test_questions("事後テスト", st.session_state.user_id)
                if not qs:
                    st.error("問題データの読み込みに失敗しました。データベースを確認してください。")
                else:
                    st.session_state.test_questions = qs
                    st.session_state.test_index = 0
                    st.session_state.test_user_answers = {}
                    st.session_state.current_test_type = "事後テスト"
                    st.session_state.start_time = time.time()
                    st.session_state.test_mode = "TEST_RUN"
                    logger.info(f"POST_TEST_START: user_id={st.session_state.user_id}")
                    st.rerun()
            if not can_start:
                st.caption("⚠️ 事前テスト完了後に開放されます。")

# 【2. テスト解答画面】
elif st.session_state.test_mode == "TEST_RUN":
    q_list = st.session_state.test_questions
    idx = st.session_state.test_index
    total = len(q_list)
    test_type = st.session_state.current_test_type

    col_title, col_timer = st.columns([2, 1])
    with col_title:
        st.markdown(f"## 📝 {test_type} （{idx + 1} / {total} 問）")
    with col_timer:
        render_javascript_timer(int(st.session_state.start_time), TEST_LIMIT_SECONDS)

    elapsed_time = time.time() - st.session_state.start_time
    if elapsed_time >= TEST_LIMIT_SECONDS:
        st.error("⏰ 制限時間の7分が経過しました。自動的に解答を提出します。")
        save_and_submit_test(test_type, total)
        st.rerun()

    if idx < total:
        q = q_list[idx]
        q_id, q_term, q_sub_cat, q_text, c_a, c_b, c_c, c_d, c_ans, q_kind = q

        st.progress((idx + 1) / total)
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
                    st.session_state.test_user_answers[idx] = {
                        "q_id": q_id, "term": q_term, "sub_cat": q_sub_cat,
                        "selected_choice": selected_char, "correct_ans": c_ans
                    }
                    st.session_state.test_index -= 1
                    st.rerun()

        with col_next:
            btn_label = "次の問題へ ➔" if (idx + 1) < total else "テストを提出する 🏁"
            if st.button(btn_label, type="primary"):
                st.session_state.test_user_answers[idx] = {
                    "q_id": q_id, "term": q_term, "sub_cat": q_sub_cat,
                    "selected_choice": selected_char, "correct_ans": c_ans
                }

                if (idx + 1) < total:
                    st.session_state.test_index += 1
                    st.rerun()
                else:
                    save_and_submit_test(test_type, total)
                    st.rerun()

# 【3. 提出完了画面（スコア・正誤は非表示）】
elif st.session_state.test_mode == "RESULT_VIEW":
    test_type = st.session_state.current_test_type
    st.title(f"✅ {test_type} 提出完了")
    st.success(f"お疲れさまでした！**{test_type}** の解答データを正常に記録しました。")

    if test_type == "事前テスト":
        st.info("👉 続いて、実験担当者の指示に従い **学習支援システム「FE-AI Tutor」** での学習に進んでください。")
    else:
        st.info("👉 すべてのテストが終了しました。実験担当者の案内に従い、**事後アンケート** への回答をお願いします。")

    if st.button("🏠 ホームへ戻る", type="primary"):
        st.session_state.test_mode = "HOME"
        st.rerun()