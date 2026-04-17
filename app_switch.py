import streamlit as st
import pandas as pd
import gspread
import base64
from google.oauth2.service_account import Credentials
import json

# --- 1. ページ設定 ---
st.set_page_config(page_title="シフト希望提出システム", layout="centered")

# --- 2. 安全な認証処理 ---
def get_gspread_client():
    # Secretsからサービスアカウント情報を読み込む
    auth_info = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(auth_info, scopes=scopes)
    return gspread.authorize(creds)

# --- 3. ログイン・認証制御 (URLパラメータ対応) ---
st.title("🙋‍♂️ シフト希望提出")

# URLパラメータ (?store=...) を取得
query_params = st.query_params
authenticated = False
target_ss_url = ""

if "store" in query_params:
    # パラメータがある場合：自動ログイン試行
    try:
        encoded_url = query_params["store"]
        target_ss_url = base64.b64decode(encoded_url).decode()
        authenticated = True
    except:
        st.error("URLが無効です。正しいURLを店長に確認してください。")
        st.stop()
else:
    # パラメータがない場合：手動パスワード認証
    password = st.text_input("店舗パスワードを入力してください", type="password")
    if password == st.secrets["app_password"]:
        authenticated = True
        target_ss_url = st.secrets["spreadsheet_url"]
    elif password:
        st.error("パスワードが違います")
        st.stop()
    else:
        st.info("URLリンクからアクセスするか、パスワードを入力してください。")
        st.stop()

# --- 4. データの読み込み ---
if authenticated:
    client = get_gspread_client()

    @st.cache_data(ttl=10)
    def load_data(url):
        sh = client.open_by_url(url)
        req = pd.DataFrame(sh.worksheet("Requirements").get_all_records())
        pref = pd.DataFrame(sh.worksheet("Preferences").get_all_records())
        return req, pref

    try:
        req_data, all_prefs = load_data(target_ss_url)
    except Exception as e:
        st.error("データの読み込みに失敗しました。URLが正しいか、共有設定を確認してください。")
        st.stop()

    # --- 5. 入力フォーム (これまでの機能) ---
    name = st.text_input("あなたの名前（フルネーム）")

    if name:
        # 既存の希望を確認
        user_prefs = all_prefs[all_prefs["名前"] == name] if not all_prefs.empty else pd.DataFrame()
        
        # 役割の選択
        role_cols = [c for c in req_data.columns if c not in ["日付", "時間"]]
        st.subheader("🛠 担当できる役割")
        able_roles = []
        cols = st.columns(len(role_cols))
        for i, r in enumerate(role_cols):
            default_val = True
            if not user_prefs.empty:
                # 過去に「不可(-100)」に設定していた役割はチェックを外す
                if user_prefs[user_prefs["役割"] == r]["希望"].min() <= -100: 
                    default_val = False
            if cols[i].checkbox(r, value=default_val): 
                able_roles.append(r)

        # 日付ごとの入力
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
                            try: 
                                default_idx = options.index(t_pref.iloc[0]["希望"])
                            except: 
                                default_idx = 0
                    
                    st.selectbox(f"【{t}】の希望", options, index=default_idx, 
                                 format_func=lambda x: {100:"◎ (入りたい)", 30:"△ (入れる)", 0:"× (休み希望)", -100:"不可"}[x], 
                                 key=f"p_{d}_{t}")

        if st.button("希望を送信する", type="primary"):
            if not name:
                st.warning("名前を入力してください。")
            else:
                with st.spinner("送信中..."):
                    new_list = []
                    for d in unique_dates:
                        for t in req_data[req_data["日付"] == d]["時間"].tolist():
                            score = st.session_state[f"p_{d}_{t}"]
                            for r in role_cols:
                                # チェックしていない役割は強制的に「不可」
                                final_score = score if r in able_roles else -100
                                new_list.append({"名前": name, "日付": d, "時間": t, "役割": r, "希望": final_score})
                    
                    # スプレッドシート上書き保存
                    sh = client.open_by_url(target_ss_url)
                    ws = sh.worksheet("Preferences")
                    other_prefs = all_prefs[all_prefs["名前"] != name] if not all_prefs.empty else pd.DataFrame()
                    final_df = pd.concat([other_prefs, pd.DataFrame(new_list)], ignore_index=True)
                    ws.clear()
                    ws.update([final_df.columns.values.tolist()] + final_df.values.tolist())
                    st.success("無事に送信されました。お疲れ様でした！")
