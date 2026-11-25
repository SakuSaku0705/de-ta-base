"""
【FE-AI Tutor】評価実験専用版（重点7分野 × 各15用語 ＝ 計105用語限定）
- 既存のUI・ログ計測・GitHub自動バックアップ機能を維持しつつ、実験対象105用語のみを表示・出題
- 実験条件切り替え（提案型フル機能 vs 従来型シンプル表示）対応
"""

import os
import re
import json
import time
import math
import random
import base64
import urllib.request
import urllib.error
import sqlite3
import datetime
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="FE-AI Tutor | 学習支援システム（評価実験版）",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "fe_study.db"
EXP_TERMS_FILE = "experiment_105_terms.json"

TARGET_7_CATEGORIES = [
    "3. コンピュータ構成要素",
    "5. ソフトウェア",
    "9. データベース",
    "10. ネットワーク",
    "11. セキュリティ",
    "12. システム開発技術",
    "22. 企業活動"
]

# 本番試験（科目A）の出題比率に基づく重点7分野の重み係数（合計1.0）
CATEGORY_WEIGHTS = {
    "3. コンピュータ構成要素": 0.14,
    "5. ソフトウェア": 0.12,
    "9. データベース": 0.14,
    "10. ネットワーク": 0.16,
    "11. セキュリティ": 0.20,
    "12. システム開発技術": 0.12,
    "22. 企業活動": 0.12
}

st.markdown("""
<style>
    .main-title { font-size: 2.1rem; font-weight: 800; color: #1E3A8A; margin-bottom: 0.2rem; }
    .badge-cat { background-color: #EFF6FF; color: #1D4ED8; padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.85rem; font-weight: 600; display: inline-block; margin-bottom: 0.6rem; }
    .badge-target { background-color: #FEF3C7; color: #92400E; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 700; margin-left: 0.5rem; }
    .overview-box { background-color: #F8FAFC; border-left: 5px solid #2563EB; padding: 1.2rem; border-radius: 6px; margin-bottom: 1.4rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .overview-title { font-size: 1.05rem; font-weight: 700; color: #1E293B; margin-bottom: 0.4rem; }
    .overview-text { font-size: 0.98rem; line-height: 1.6; color: #334155; }
    .content-box { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 1.2rem; line-height: 1.8; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 厳選105用語の読み込み（JSON優先、未作成時はDBから各分野15用語を自動抽出）
# =========================================================
@st.cache_data
def get_experiment_105_terms():
    if os.path.exists(EXP_TERMS_FILE):
        try:
            with open(EXP_TERMS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                terms = data.get("terms", [])
                if terms:
                    return set(terms)
        except Exception:
            pass

    # JSONが無い場合のフォールバック：DBからイラスト付き優先で各分野15用語を取得
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT term_name FROM terms_master WHERE question_text IS NOT NULL AND TRIM(question_text) != ''")
    valid_q_terms = {r["term_name"].strip() for r in cur.fetchall()}

    selected = set()
    for cat in TARGET_7_CATEGORIES:
        cur.execute("SELECT term_name, image_path FROM terms WHERE sub_category LIKE ?", (f"%{cat}%",))
        scored = []
        for r in cur.fetchall():
            t = r["term_name"].strip()
            if t not in valid_q_terms:
                continue
            p = str(r["image_path"] or "").strip()
            has_img = 1 if (p and p not in ("None", "nan") and os.path.exists(p)) else 0
            scored.append((-has_img, t))
        scored.sort()
        for _, t in scored[:15]:
            selected.add(t)
    conn.close()
    return selected

EXP_105_SET = get_experiment_105_terms()

# =========================================================
# GitHub 自動ログ追記関数
# =========================================================
def append_log_to_github(timestamp_str, user_id, action_type, term_name, detail, is_correct, duration_sec):
    """Streamlit Secretsに設定されたGitHubリポジトリのCSVファイルに1行追記する"""
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        repo = st.secrets.get("GITHUB_REPO")
        file_path = st.secrets.get("LOG_FILE_PATH", "experiment_logs.csv")
    except Exception:
        return

    if not token or not repo:
        return

    api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "FE-AI-Tutor-Logger"
    }

    safe_term = str(term_name).replace('"', '""')
    safe_detail = str(detail).replace('"', '""')
    new_row = f'"{timestamp_str}","{user_id}","{action_type}","{safe_term}","{safe_detail}","{is_correct}",{duration_sec}\n'
    header_row = "timestamp,user_id,action_type,term_name,detail,is_correct,duration_seconds\n"

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
        "message": f"log: {user_id} - {action_type} ({term_name})",
        "content": encoded_content
    }
    if sha:
        payload["sha"] = sha

    try:
        put_req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT"
        )
        urllib.request.urlopen(put_req, timeout=5)
    except Exception:
        pass


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
        response_time_seconds REAL DEFAULT 0,
        answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("PRAGMA table_info(quiz_logs);")
    q_cols = [c[1] for c in cur.fetchall()]
    if "question_type" not in q_cols:
        cur.execute("ALTER TABLE quiz_logs ADD COLUMN question_type TEXT DEFAULT 'Q1';")
    if "response_time_seconds" not in q_cols:
        cur.execute("ALTER TABLE quiz_logs ADD COLUMN response_time_seconds REAL DEFAULT 0;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS term_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        term_name TEXT,
        duration_seconds REAL DEFAULT 0,
        viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("PRAGMA table_info(term_logs);")
    t_cols = [c[1] for c in cur.fetchall()]
    if "duration_seconds" not in t_cols:
        cur.execute("ALTER TABLE term_logs ADD COLUMN duration_seconds REAL DEFAULT 0;")

    conn.commit()
    conn.close()

init_log_tables()


def now_jst_str():
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")


def flush_term_duration(conn):
    """直前に閲覧していた用語の滞在時間を確定してDBとGitHubに保存する"""
    if "active_term" in st.session_state and st.session_state["active_term"]:
        elapsed = round(time.time() - st.session_state["term_start_time"], 1)
        if 1.0 <= elapsed <= 600.0:
            ts = now_jst_str()
            uid = st.session_state["user_id"]
            tname = st.session_state["active_term"]
            cond = st.session_state.get("exp_condition", "proposed")

            cur = conn.cursor()
            cur.execute("""
                INSERT INTO term_logs (user_id, term_name, duration_seconds, viewed_at)
                VALUES (?, ?, ?, ?);
            """, (uid, tname, elapsed, ts))
            conn.commit()

            append_log_to_github(ts, uid, "TERM_STUDY", tname, f"view_{cond}", "-", elapsed)

        st.session_state["active_term"] = None


def build_weighted_question_set(cur, sel_cat, q_type_code, num_questions):
    """
    厳選105用語（EXP_105_SET）の中から、本番出題比率または指定分野でランダム抽出する
    """
    cond_col = "question_text" if q_type_code == "Q1" else "q2_question_text"
    sampled_terms = []

    if sel_cat == "本番頻度重み付け（重点7分野ミックス）":
        allocations = {}
        allocated_sum = 0
        for cat, weight in CATEGORY_WEIGHTS.items():
            cnt = int(math.floor(num_questions * weight))
            allocations[cat] = cnt
            allocated_sum += cnt

        remainder = num_questions - allocated_sum
        sorted_cats_by_weight = sorted(CATEGORY_WEIGHTS.keys(), key=lambda c: CATEGORY_WEIGHTS[c], reverse=True)
        for i in range(remainder):
            target_c = sorted_cats_by_weight[i % len(sorted_cats_by_weight)]
            allocations[target_c] += 1

        for cat, target_cnt in allocations.items():
            if target_cnt <= 0:
                continue
            cur.execute(
                f"SELECT term_name FROM terms_master WHERE sub_category LIKE ? AND {cond_col} IS NOT NULL AND TRIM({cond_col}) != '';",
                (f"%{cat}%",)
            )
            rows = [r["term_name"] for r in cur.fetchall() if r["term_name"].strip() in EXP_105_SET]
            random.shuffle(rows)
            sampled_terms.extend(rows[:target_cnt])

        # 不足分があれば105用語全体から重複なしで補充
        if len(sampled_terms) < num_questions:
            shortage = num_questions - len(sampled_terms)
            cur.execute(
                f"SELECT term_name FROM terms_master WHERE {cond_col} IS NOT NULL AND TRIM({cond_col}) != '';"
            )
            pool = [r["term_name"] for r in cur.fetchall() if r["term_name"].strip() in EXP_105_SET and r["term_name"] not in sampled_terms]
            random.shuffle(pool)
            sampled_terms.extend(pool[:shortage])

        random.shuffle(sampled_terms)
    else:
        cur.execute(
            f"SELECT term_name FROM terms_master WHERE sub_category = ? AND {cond_col} IS NOT NULL AND TRIM({cond_col}) != '';",
            (sel_cat,)
        )
        rows = [r["term_name"] for r in cur.fetchall() if r["term_name"].strip() in EXP_105_SET]
        random.shuffle(rows)
        sampled_terms = rows[:num_questions]

    return sampled_terms[:num_questions]


# =========================================================
# 1. ログイン画面
# =========================================================
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "active_term" not in st.session_state:
    st.session_state["active_term"] = None
if "term_start_time" not in st.session_state:
    st.session_state["term_start_time"] = time.time()
if "exp_condition" not in st.session_state:
    st.session_state["exp_condition"] = "proposed"

if not st.session_state["user_id"]:
    st.title("🎓 FE-AI Tutor ログイン（評価実験版）")
    st.caption("基本情報技術者試験（科目A）重点7分野・厳選105用語 学習支援システム")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 被験者ログイン")
        user_input = st.text_input("被験者IDを入力してください:", placeholder="例: user01")
        cond_label = st.radio(
            "実験条件（担当者の指示どおり選択してください）:",
            ["提案システム（図解・比喩・実例・詳細解説あり）", "比較用従来型（公式定義・問題演習のみ）"]
        )
        if st.button("学習を開始する", type="primary"):
            if user_input.strip():
                uid = user_input.strip()
                cond_code = "proposed" if "提案システム" in cond_label else "baseline"
                st.session_state["user_id"] = uid
                st.session_state["exp_condition"] = cond_code
                append_log_to_github(now_jst_str(), uid, "LOGIN", "-", f"start_{cond_code}", "-", 0)
                st.rerun()
            else:
                st.warning("IDを入力してください。")
    with col2:
        st.info("""
        **【学習の進め方（推奨ガイド）】**
        - **前半（約15分）：「💡 用語学習」**
          重点7分野（各15用語）から気になる用語を選び、構造や意味を確認しましょう。
        - **後半（約10分）：「📝 問題演習」**
          10問セットなどで理解度を確認しましょう。
        - 終了時は必ず左側の**「ログアウト」**ボタンを押してください。
        """)
    st.stop()

conn = get_db()
cur = conn.cursor()
is_proposed = (st.session_state.get("exp_condition", "proposed") == "proposed")

# =========================================================
# 2. サイドバー
# =========================================================
st.sidebar.markdown(f"👤 **ログイン中:** `{st.session_state['user_id']}`")
if st.sidebar.button("ログアウト"):
    flush_term_duration(conn)
    append_log_to_github(now_jst_str(), st.session_state["user_id"], "LOGOUT", "-", f"end_{st.session_state.get('exp_condition')}", "-", 0)
    st.session_state["user_id"] = None
    st.rerun()

st.sidebar.divider()
mode = st.sidebar.radio("📚 モードを選択", ["💡 用語学習", "📝 問題演習", "📊 学習履歴・分析"])

if mode != "💡 用語学習":
    flush_term_duration(conn)

def sort_categories(cat_list):
    def get_num(cat_str):
        m = re.match(r"^(\d+)", cat_str)
        return int(m.group(1)) if m else 999
    return sorted(cat_list, key=get_num)

# =========================================================
# 3. モード別画面
# =========================================================

# ---------------------------------------------------------
# A. 用語学習モード（重点7分野 × 各15用語限定）
# ---------------------------------------------------------
if mode == "💡 用語学習":
    st.sidebar.subheader("🔍 用語を探す（厳選105用語）")
    
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
        search_results = [r for r in cur.fetchall() if r["term_name"].strip() in EXP_105_SET]

        if search_results:
            result_options = {f"{r['term_name']} （{r['sub_category']}）": r['term_name'] for r in search_results}
            selected_display = st.sidebar.selectbox(f"検索結果 ({len(search_results)}件):", list(result_options.keys()))
            selected_term = result_options[selected_display]
        else:
            st.sidebar.warning(f"「{search_keyword}」に一致する用語は見つかりませんでした。")
    else:
        cur.execute("SELECT DISTINCT sub_category FROM terms WHERE sub_category IS NOT NULL;")
        raw_cats = [
            row["sub_category"] for row in cur.fetchall()
            if any(t_cat in str(row["sub_category"]) for t_cat in TARGET_7_CATEGORIES)
        ]
        sorted_cats = sort_categories(raw_cats)

        cat_display_map = {f"🚩 {c}": c for c in sorted_cats}

        selected_label = st.sidebar.selectbox("📂 重点7分野を選択", list(cat_display_map.keys()))
        selected_cat = cat_display_map[selected_label]

        cur.execute("SELECT term_name FROM terms WHERE sub_category = ? ORDER BY term_name;", (selected_cat,))
        terms = [row["term_name"] for row in cur.fetchall() if row["term_name"].strip() in EXP_105_SET]
        selected_term = st.sidebar.selectbox(f"🔍 用語を選択（全{len(terms)}語）", terms)

    if selected_term:
        if st.session_state["active_term"] != selected_term:
            flush_term_duration(conn)
            st.session_state["active_term"] = selected_term
            st.session_state["term_start_time"] = time.time()

        cur.execute("SELECT * FROM terms WHERE term_name = ?;", (selected_term,))
        tdata = cur.fetchone()

        if tdata:
            badge_html = f'<div class="badge-cat">分類: {tdata["sub_category"]}</div>'
            badge_html += '<span class="badge-target">★ 実験対象 重点7分野</span>'
            st.markdown(badge_html, unsafe_allow_html=True)
            st.markdown(f'<div class="main-title">{tdata["term_name"]}</div>', unsafe_allow_html=True)

            off_def = tdata["official_def"]
            if not off_def or str(off_def).strip() in ["", "None", "nan"]:
                off_def = "※ 公式定義データを読み込み中（シラバス標準定義に準拠）。"

            st.markdown(f"""
            <div class="overview-box">
                <div class="overview-title">📌 用語の概要（基本定義）</div>
                <div class="overview-text">{off_def}</div>
            </div>
            """, unsafe_allow_html=True)

            # 提案システム（フル機能）の場合のみ図解と3タブ多層解説を表示
            if is_proposed:
                img_path = tdata["image_path"]
                if img_path and os.path.exists(img_path):
                    st.markdown("##### 🖼️ 構造対比インフォグラフィック")
                    st.image(img_path, caption=f"【概念図解】{tdata['term_name']}", use_container_width=True)
                    st.write("")

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
# B. 問題演習モード（重点7分野 × 各15用語限定）
# ---------------------------------------------------------
elif mode == "📝 問題演習":
    st.title("📝 基本情報技術者（科目A）問題演習")
    st.caption("重点7分野（厳選105用語）から、重み付けまたは分野指定で実践演習を行います。")

    cur.execute("SELECT DISTINCT sub_category FROM terms_master WHERE question_text IS NOT NULL;")
    raw_q_cats = [
        r["sub_category"] for r in cur.fetchall()
        if any(tc in str(r["sub_category"]) for tc in TARGET_7_CATEGORIES)
    ]
    sorted_q_cats = sort_categories(raw_q_cats)

    col_q1, col_q2 = st.columns([1, 2])
    with col_q1:
        st.markdown("#### ⚙️ 演習セット設定")
        q_options = ["🎯 本番頻度重み付け（重点7分野ミックス）"]
        q_map = {"🎯 本番頻度重み付け（重点7分野ミックス）": "本番頻度重み付け（重点7分野ミックス）"}
        for qc in sorted_q_cats:
            label = f"✨ {qc}"
            q_options.append(label)
            q_map[label] = qc

        sel_q_label = st.selectbox("出題モード・分野を選択", q_options)
        sel_q_cat = q_map[sel_q_label]

        q_type = st.radio("問題タイプ", ["【基本】正解を見抜く問題 (Q1)", "【応用】誤りを見抜く問題 (Q2)"])
        q_type_code = "Q1" if "Q1" in q_type else "Q2"

        num_questions = st.selectbox("出題問題数を選択", [10, 15, 20, 30], index=0, format_func=lambda x: f"{x} 問セット")

        if st.button("🚀 新しい演習セットを開始（リセット）", type="secondary", use_container_width=True):
            st.session_state["quiz_queue"] = build_weighted_question_set(cur, sel_q_cat, q_type_code, num_questions)
            st.session_state["quiz_index"] = 0
            st.session_state["quiz_score"] = 0
            st.session_state["quiz_answered"] = False
            st.session_state["quiz_config_sig"] = f"{sel_q_cat}_{q_type_code}_{num_questions}"
            st.session_state["q_start_time"] = time.time()
            st.rerun()

    current_sig = f"{sel_q_cat}_{q_type_code}_{num_questions}"
    if st.session_state.get("quiz_config_sig") != current_sig or "quiz_queue" not in st.session_state:
        st.session_state["quiz_queue"] = build_weighted_question_set(cur, sel_q_cat, q_type_code, num_questions)
        st.session_state["quiz_index"] = 0
        st.session_state["quiz_score"] = 0
        st.session_state["quiz_answered"] = False
        st.session_state["quiz_config_sig"] = current_sig
        st.session_state["q_start_time"] = time.time()

    queue = st.session_state.get("quiz_queue", [])
    idx = st.session_state.get("quiz_index", 0)
    total_in_set = len(queue)

    with col_q2:
        if total_in_set == 0:
            st.warning("選択された条件に該当する問題が見つかりませんでした。別の分野や問題タイプをお試しください。")
        elif idx >= total_in_set:
            score = st.session_state.get("quiz_score", 0)
            rate = (score / total_in_set) * 100
            st.success(f"🎊 演習セット完了！ 成績: **{score} / {total_in_set} 問正解（正答率 {rate:.1f}%）**")
            if st.button("🔄 同じ設定でもう1セット解く", type="primary"):
                st.session_state["quiz_queue"] = build_weighted_question_set(cur, sel_q_cat, q_type_code, num_questions)
                st.session_state["quiz_index"] = 0
                st.session_state["quiz_score"] = 0
                st.session_state["quiz_answered"] = False
                st.session_state["q_start_time"] = time.time()
                st.rerun()
        else:
            st.progress((idx + 1) / total_in_set, text=f"進捗: 第 {idx + 1} 問 / 全 {total_in_set} 問 （現在の正解数: {st.session_state.get('quiz_score', 0)}問）")
            current_term = queue[idx]
            cur.execute("SELECT * FROM terms_master WHERE term_name = ?;", (current_term,))
            q_data = cur.fetchone()

            if q_data:
                st.markdown(f"**対象用語**: `{q_data['term_name']}` （分野: {q_data['sub_category']}）")

                if q_type_code == "Q1":
                    st.markdown(f"#### Q{idx + 1}. {q_data['question_text']}")
                    choices = [
                        f"ア: {q_data['choice_a']}",
                        f"イ: {q_data['choice_b']}",
                        f"ウ: {q_data['choice_c']}",
                        f"エ: {q_data['choice_d']}"
                    ]
                    ans = st.radio("あなたの回答:", choices, key=f"q1_{idx}_{q_data['term_name']}")

                    if st.button("解答を送信", type="primary", key=f"btn_submit_q1_{idx}", disabled=st.session_state.get("quiz_answered", False)):
                        resp_sec = round(time.time() - st.session_state.get("q_start_time", time.time()), 1)
                        correct = q_data["correct_ans"]
                        is_corr = 1 if ans.startswith(correct) else 0
                        ts = now_jst_str()
                        uid = st.session_state["user_id"]

                        cur.execute("""
                            INSERT INTO quiz_logs (user_id, term_name, question_type, selected_choice, is_correct, response_time_seconds, answered_at)
                            VALUES (?, ?, 'Q1', ?, ?, ?, ?);
                        """, (uid, q_data["term_name"], ans[:1], is_corr, resp_sec, ts))
                        conn.commit()

                        append_log_to_github(ts, uid, "QUIZ_Q1", q_data["term_name"], ans[:1], is_corr, resp_sec)

                        st.session_state["quiz_answered"] = True
                        st.session_state["last_is_corr"] = is_corr
                        st.session_state["last_resp_sec"] = resp_sec
                        if is_corr:
                            st.session_state["quiz_score"] += 1
                        st.rerun()

                    if st.session_state.get("quiz_answered", False):
                        correct = q_data["correct_ans"]
                        if st.session_state.get("last_is_corr"):
                            st.success(f"🎉 正解です！（正解: {correct} / 解答時間: {st.session_state.get('last_resp_sec')}秒）")
                        else:
                            st.error(f"不正解です。（正解: {correct} / 解答時間: {st.session_state.get('last_resp_sec')}秒）")

                        if is_proposed:
                            with st.expander("💡 初学者向け分かりやすい解説", expanded=True):
                                st.write(q_data["explanation_beginner"])
                            with st.expander("🔬 理系・技術的詳細解説", expanded=True):
                                st.write(q_data["explanation_advanced"])

                        if st.button("➡️ 次の問題へ進む", type="primary", key=f"next_q1_{idx}"):
                            st.session_state["quiz_index"] += 1
                            st.session_state["quiz_answered"] = False
                            st.session_state["q_start_time"] = time.time()
                            st.rerun()

                else:
                    st.markdown(f"#### Q{idx + 1}（不適切なものを選択）. {q_data['q2_question_text']}")
                    choices2 = [
                        f"ア: {q_data['q2_choice_a']}",
                        f"イ: {q_data['q2_choice_b']}",
                        f"ウ: {q_data['q2_choice_c']}",
                        f"エ: {q_data['q2_choice_d']}"
                    ]
                    ans2 = st.radio("あなたの回答:", choices2, key=f"q2_{idx}_{q_data['term_name']}")

                    if st.button("解答を送信", type="primary", key=f"btn_submit_q2_{idx}", disabled=st.session_state.get("quiz_answered", False)):
                        resp_sec2 = round(time.time() - st.session_state.get("q_start_time", time.time()), 1)
                        correct2 = q_data["q2_correct_ans"]
                        is_corr2 = 1 if ans2.startswith(correct2) else 0
                        ts2 = now_jst_str()
                        uid = st.session_state["user_id"]

                        cur.execute("""
                            INSERT INTO quiz_logs (user_id, term_name, question_type, selected_choice, is_correct, response_time_seconds, answered_at)
                            VALUES (?, ?, 'Q2', ?, ?, ?, ?);
                        """, (uid, q_data["term_name"], ans2[:1], is_corr2, resp_sec2, ts2))
                        conn.commit()

                        append_log_to_github(ts2, uid, "QUIZ_Q2", q_data["term_name"], ans2[:1], is_corr2, resp_sec2)

                        st.session_state["quiz_answered"] = True
                        st.session_state["last_is_corr"] = is_corr2
                        st.session_state["last_resp_sec"] = resp_sec2
                        if is_corr2:
                            st.session_state["quiz_score"] += 1
                        st.rerun()

                    if st.session_state.get("quiz_answered", False):
                        correct2 = q_data["q2_correct_ans"]
                        if st.session_state.get("last_is_corr"):
                            st.success(f"🎉 正解です！（不適切な選択肢: {correct2} / 解答時間: {st.session_state.get('last_resp_sec')}秒）")
                        else:
                            st.error(f"不正解です。（正解: {correct2} / 解答時間: {st.session_state.get('last_resp_sec')}秒）")

                        if is_proposed:
                            with st.expander("💡 解説を確認する", expanded=True):
                                st.write(q_data["q2_exp_beginner_final"])

                        if st.button("➡️ 次の問題へ進む", type="primary", key=f"next_q2_{idx}"):
                            st.session_state["quiz_index"] += 1
                            st.session_state["quiz_answered"] = False
                            st.session_state["q_start_time"] = time.time()
                            st.rerun()

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

        show_cols = ["term_name", "question_type", "selected_choice", "is_correct", "response_time_seconds", "answered_at"]
        available_cols = [c for c in show_cols if c in df_logs.columns]

        st.subheader("直近の回答履歴")
        st.dataframe(df_logs[available_cols], use_container_width=True)
    else:
        st.info("まだ演習履歴がありません。『📝 問題演習』から問題を解いてみましょう！")

conn.close()