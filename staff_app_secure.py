import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# --- 1. ページ設定 ---
st.set_page_config(page_title="シフト希望提出システム", layout="wide")

# --- 2. 管理者設定（サイドバー） ---
st.sidebar.title("⚙ 管理者設定")
st.sidebar.info("初めて使う店長は、ここで自分のシート情報を設定してください。")

# セッション状態（ブラウザを閉じるまで保持されるメモリ）の初期化
if "config" not in st.session_state:
    st.session_state.config = {
        "url": os.environ.get("spreadsheet_url", ""),
        "json": os.environ.get("gcp_service_account", ""),
        "pw": os.environ.get("app_password", "")
    }

with st.sidebar.expander("🔑 接続情報を設定する"):
    new_url = st.text_input("スプレッドシートURL", value=st.session_state.config["url"])
    new_json = st.text_area("Google JSONの中身", value=st.session_state.config["json"], help="GoogleからダウンロードしたJSONの中身を全て貼ってください")
    new_pw = st.text_input("店舗パスワード（従業員用）", value=st.session_state.config["pw"], type="password")
    
    if st.button("設定を更新する"):
        st.session_state.config["url"] = new_url
        st.session_state.config["json"] = new_json
        st.session_state.config["pw"] = new_pw
        st.success("設定を一時保存しました！")

# --- 3. 安全な認証処理 ---
def get_gspread_client():
    try:
        auth_info = json.loads(st.session_state.config["json"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(auth_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception:
        return None

# --- 4. 簡易パスワード認証 ---
st.title("🙋‍♂️ シフト希望提出")
password = st.text_input("店舗パスワードを入力してください", type="password")

# 設定されたパスワードと照合
if password != st.session_state.config["pw"]: 
    if password:
        st.error("パスワードが違います")
    st.info("左側の設定が完了し、正しいパスワードを入力すると画面が表示されます")
    st.stop()

# --- 5. データの読み込み ---
client = get_gspread_client()
if client is None:
    st.warning("👈 左側の設定から『Google JSONの中身』を正しく入力してください")
    st.stop()

spreadsheet_url = st.session_state.config["url"]

@st.cache_data(ttl=10)
def load_data(url):
    sh = client.open_by_url(url)
    req = pd.DataFrame(sh.worksheet("Requirements").get_all_records())
    pref = pd.DataFrame(sh.worksheet("Preferences").get_all_records())
    return req, pref

try:
    req_data, all_prefs = load_data(spreadsheet_url)
except Exception as e:
    st.error("スプレッドシートの読み込みに失敗しました。URLと共有設定を確認してください。")
    st.stop()

# --- 6. 入力フォーム（以下、以前と同じ） ---
name = st.text_input("あなたの名前（フルネーム）")

if name:
    # (中略：以前の入力フォームの処理がここに入ります)
    st.write(f"ようこそ {name} さん！")
    # ...（送信ボタンなどの処理）
