import streamlit as st
import pandas as pd
import gspread
import base64
import json
from google.oauth2.service_account import Credentials

# --- 1. ページ設定 ---
st.set_page_config(page_title="シフト希望提出システム", layout="centered")

# --- 2. 認証処理の定義 ---
def get_gspread_client_from_json(json_data):
    """引数でもらったJSONデータで認証する"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json_data, scopes=scopes)
    return gspread.authorize(creds)

def get_master_client():
    """あなたのSecretsにある共通鍵で認証する（最初の読み込み用）"""
    auth_info = st.secrets["gcp_service_account"]
    return get_gspread_client_from_json(auth_info)

# --- 3. 自動ログイン・データ取得ロジック ---
st.title("🙋‍♂️ シフト希望提出")

query_params = st.query_params
authenticated = False
target_ss_url = ""
client = None

# A. URLパラメータがある場合 (店長発行のURL)
if "store" in query_params:
    try:
        encoded_url = query_params["store"]
        target_ss_url = base64.b64decode(encoded_url).decode()
        
        # 1. あなたのマスター鍵で、そのシートの「SystemConfig」を読みに行く
        master_client = get_master_client()
        sh = master_client.open_by_url(target_ss_url)
        config_ws = sh.worksheet("SystemConfig")
        
        # 2. B2セルに保存されている統合設定データを取得
        val = config_ws.acell("B2").value
        config_all = json.loads(val)
        
        # 3. 店長専用のJSON鍵を取り出す
        store_json_data = config_all["JSON_KEY"]
        
        # 4. 【追加】管理者側で保存したカスタム設定（役割など）を復元
        if "SETTINGS" in config_all:
            settings = config_all["SETTINGS"]
            # セッションに保存して後の処理で使えるようにする
            if "roles" in settings:
                st.session_state.last_roles = settings["roles"]
            if "custom_blocks" in settings:
                st.session_state.custom_blocks = settings["custom_blocks"]
        
        # 5. その店長専用の鍵で再ログイン
        client = get_gspread_client_from_json(store_json_data)
        authenticated = True
        
    except Exception as e:
        # デバッグ用：必要に応じて st.error(f"詳細: {e}") に書き換えてください
        st.error("自動ログインに失敗しました。URLが正しいか、管理者が『紐付け』済みか確認してください。")
        st.stop()

# B. パラメータがない場合 (従来のパスワード認証)
else:
    # (既存のパスワード認証ロジック)
    password = st.text_input("店舗パスワードを入力してください", type="password")
    if password == st.secrets["app_password"]:
        target_ss_url = st.secrets["spreadsheet_url"]
        client = get_master_client()
        authenticated = True
    elif password:
        st.error("パスワードが違います")
        st.stop()
    else:
        st.info("URLリンクからアクセスするか、パスワードを入力してください。")
        st.stop()

# --- 4. データの読み込みとフォーム表示 ---
if authenticated and client:
    @st.cache_data(ttl=10)
    def load_data(url):
        sh = client.open_by_url(url)
        req = pd.DataFrame(sh.worksheet("Requirements").get_all_records())
        pref = pd.DataFrame(sh.worksheet("Preferences").get_all_records())
        return req, pref

    try:
        req_data, all_prefs = load_data(target_ss_url)
    except Exception as e:
        st.error("データの取得に失敗しました。シート名(Requirements/Preferences)を確認してください。")
        st.stop()

    # --- 5. 入力フォーム (4段階評価に統一) ---
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
                # 過去にその役割で「不可(-100)」が1つでもあればチェックを外す
                if user_prefs[user_prefs["役割"] == r]["希望"].min() <= -100: 
                    default_val = False
            if cols[i].checkbox(r, value=default_val): 
                able_roles.append(r)

        st.subheader("📅 出勤希望の回答")
        unique_dates = sorted(req_data["日付"].unique())
        
        # 4段階評価の定義（共通）
        options = [100, 30, 0, -100]
        format_map = {100: "◎ (入りたい)", 30: "△ (入れる)", 0: "× (休み希望)", -100: "不可"}
        
        for d in unique_dates:
            with st.expander(f"📅 {d} の希望"):
                # その日の募集枠を取得（時間刻み or 固定枠名）
                day_slots = req_data[req_data["日付"] == d]["時間"].tolist()
                for t in day_slots:
                    default_idx = 0
                    if not user_prefs.empty:
                        t_pref = user_prefs[(user_prefs["日付"] == d) & (user_prefs["時間"] == t)]
                        if not t_pref.empty: 
                            try:
                                # 前回の回答を再現
                                default_idx = options.index(t_pref.iloc[0]["希望"])
                            except:
                                default_idx = 0
                    
                    st.selectbox(
                        f"【{t}】の希望", 
                        options, 
                        index=default_idx, 
                        format_func=lambda x: format_map[x], 
                        key=f"p_{d}_{t}"
                    )

        if st.button("希望を送信する", type="primary"):
            if not name:
                st.warning("名前を入力してください。")
            elif not able_roles:
                st.warning("担当できる役割を少なくとも1つ選択してください。")
            else:
                with st.spinner("送信中..."):
                    new_list = []
                    for d in unique_dates:
                        day_slots = req_data[req_data["日付"] == d]["時間"].tolist()
                        for t in day_slots:
                            # セレクトボックスで選択されたスコア (100, 30, 0, -100)
                            score = st.session_state[f"p_{d}_{t}"]
                            for r in role_cols:
                                # 役割にチェックがない場合は強制的に「不可(-100)」にする
                                final_score = score if r in able_roles else -100
                                new_list.append({
                                    "名前": name, 
                                    "日付": d, 
                                    "時間": t, 
                                    "役割": r, 
                                    "希望": final_score
                                })
                    
                    # スプレッドシートへの更新処理
                    sh = client.open_by_url(target_ss_url)
                    ws = sh.worksheet("Preferences")
                    
                    # 自分の過去の回答以外を保持して結合
                    other_prefs = all_prefs[all_prefs["名前"] != name] if not all_prefs.empty else pd.DataFrame()
                    final_df = pd.concat([other_prefs, pd.DataFrame(new_list)], ignore_index=True)
                    
                    ws.clear()
                    # ヘッダー付きで一括更新
                    ws.update([final_df.columns.values.tolist()] + final_df.values.tolist())
                    st.success("無事に送信されました。お疲れ様でした！")
