# FE-AI Tutor (基本情報技術者試験 概念理解支援システム)

基本情報技術者試験（科目A）の初学者向け学習支援システム。
専門用語を排除した日常の比喩、実社会での活用例、16:9の横長概念図、属性別二層解説（初学者向け・理系向け）を提供し、直感的な理解を促します。

## 実行方法
### ライブラリのインストール
pip3 install streamlit pandas openpyxl pillow matplotlib pydantic google-genai

### appの実行
streamlit run app.py


## システムアーキテクチャ
- **Frontend / UI**: Streamlit (`app.py`)
- **Database**: SQLite (`fe_study.db`)
- **Master Dataset**: Excel (`fe_study_master_23sheets.xlsx`)
- **LLM Integration**: Google Gemini 2.5 Flash via Vertex AI

## 主要プログラム一覧

| ファイル名 | 役割・概要 |
| :--- | :--- |
| `app.py` | 学習用Webアプリケーション本体（用語学習、問題演習、学習ログ追跡） |
| `rewrite_metaphors_7categories.py` | 重要7分野の比喩・実用例を日常言語へ全面リライトする生成スクリプト |
| `evaluate_metaphors.py` | 比喩・実用例の3軸品質査読スクリプト（○/△/×判定、レジューム対応） |
| `rebuild_all_tables.py` | ExcelマスターからDB（`terms`, `terms_master`）を完全再構築・同期 |
| `generate_exam_diagrams.py` | 16:9横長概念図および試験直結テキストの生成パイプライン |
| `generate_and_save_to_excel.py` | 正当選択問題（Q1）および二層解説の自動生成スクリプト |
| `generate_q2_to_excel.py` | 不適当選択問題（Q2）および選択肢別解説の自動生成スクリプト |
| `evaluate_questions.py` | 生成された問題・選択肢・解説の整合性ファクトチェック評価スクリプト |
| `compress_images.py` | `static/images/` 内の画像容量をWeb表示用に圧縮・最適化するツール |

## データファイル
- `fe_study_master_23sheets.xlsx`: 全用語・全問題・全解説・比喩のマスターデータ
- `fe_study.db`: アプリケーション用SQLiteデータベース（ログ記録含む）
- `比喩・実用例_品質精査評価シート.xlsx`: 比喩・実用例の自動評価結果レポート
- `基本情報問題・解説_品質精査評価シート.xlsx`: 問題文・解説の自動評価結果レポート
