import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# --- 1. ページ設定 ---
st.set_page_config(page_title="シフト希望提出システム", layout="centered")

# --- 2. 安全な認証処理 (Renderの環境変数を使用) ---
def get_gspread_client():
    # RenderのEnvironment Variablesに保存したJSONを読み込む
    # ここを修正しました
    auth_info_str = os.environ.get("gcp_service_account")
    auth_info = json.loads(auth_info_str)
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(auth_info, scopes=scopes)
    return gspread.authorize(creds)

# --- 3. 簡易パスワード認証 ---
st.title("🙋‍♂️ シフト希望提出")
password = st.text_input("店舗パスワードを入力してください", type="password")

# ここも修正しました
app_password = os.environ.get("app_password")

if password != app_password: 
    if password:
        st.error("パスワードが違います")
    st.info("正しいパスワードを入力すると入力画面が表示されます")
    st.stop()

# --- 4. データの読み込み ---
client = get_gspread_client()
# ここも修正しました
spreadsheet_url = os.environ.get("spreadsheet_url") 

@st.cache_data(ttl=10)
def load_data(url):
    sh = client.open_by_url(url)
    req = pd.DataFrame(sh.worksheet("Requirements").get_all_records())
    pref = pd.DataFrame(sh.worksheet("Preferences").get_all_records())
    return req, pref

try:
    req_data, all_prefs = load_data(spreadsheet_url)
except Exception as e:
    st.error("データの読み込みに失敗しました。店長に連絡してください。")
    st.stop()

# --- 5. 入力フォーム (ここから下は変更なし) ---
name = st.text_input("あなたの名前（フルネーム）")

if name:
    user_prefs = all_prefs[all_prefs["名前"] == name] if not all_prefs.empty else pd.DataFrame()
    role_cols = [c for c in req_data.columns if c not in ["日付", "時間"]]
    st.subheader("🛠 担当できる役割")
    able_roles = []
    cols = st.columns(len(role_cols))
    for i, r in enumerate(role_cols):
        default_val = True
        if not user_prefs.empty:
            if user_prefs[user_prefs["役割"] == r]["希望"].min() <= -100: default_val = False
        if cols[i].checkbox(r, value=default_val): able_roles.append(r)

    st.subheader("📅 出勤希望の回答")
    unique_dates = sorted(req_data["日付"].unique())
    options = [100, 30, 0, -100]
    
    for d in unique_dates:
        with st.expander(f"📅 {d} の希望"):
            day_slots = req_data[req_data["日付"] == d]["時間"].tolist()
            for t in day_slots:
                default_idx = 0
                if not user_prefs.empty:
                    t_pref = user_prefs[(user_prefs["日付"] == d) & (user_prefs["時間"] == t)]
                    if not t_pref.empty: 
                        try: default_idx = options.index(t_pref.iloc[0]["希望"])
                        except: default_idx = 0
                
                st.selectbox(f"【{t}】の希望", options, index=default_idx, 
                             format_func=lambda x: {100:"◎ (入りたい)", 30:"△ (入れる)", 0:"× (休み希望)", -100:"不可"}[x], 
                             key=f"p_{d}_{t}")

    if st.button("希望を送信する", type="primary"):
        with st.spinner("送信中..."):
            new_list = []
            for d in unique_dates:
                for t in req_data[req_data["日付"] == d]["時間"].tolist():
                    score = st.session_state[f"p_{d}_{t}"]
                    for r in role_cols:
                        final_score = score if r in able_roles else -100
                        new_list.append({"名前": name, "日付": d, "時間": t, "役割": r, "希望": final_score})
            
            sh = client.open_by_url(spreadsheet_url)
            ws = sh.worksheet("Preferences")
            other_prefs = all_prefs[all_prefs["名前"] != name] if not all_prefs.empty else pd.DataFrame()
            final_df = pd.concat([other_prefs, pd.DataFrame(new_list)], ignore_index=True)
            ws.clear()
            ws.update([final_df.columns.values.tolist()] + final_df.values.tolist())
            st.success("無事に送信されました。お疲れ様でした！")
