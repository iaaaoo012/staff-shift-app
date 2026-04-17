import streamlit as st
import pandas as pd
from datetime import time, datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import json # データの変換用に追加

# ページ設定
st.set_page_config(layout="wide", page_title="シフト最適化システム")

# --- 1. Google Sheets 接続設定 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Googleスプレッドシートへの接続に失敗しました。")
    st.stop()

# --- 2. URLパラメータ判定 ---
query_params = st.query_params
is_staff_mode = query_params.get("mode") == "staff"

# --- 3. 共通関数 ---
def generate_slots(unit, start_h, end_h):
    slots = []
    current = datetime.combine(datetime.today(), time(0, 0)) + timedelta(hours=start_h)
    limit = datetime.combine(datetime.today(), time(0, 0)) + timedelta(hours=end_h)
    while current < limit:
        h = current.hour
        if current.date() > datetime.today().date(): h += 24
        slots.append(f"{h:02d}:{current.strftime('%M')}")
        current += timedelta(hours=unit)
    return slots

# --- A. 従業員専用モード ---
if is_staff_mode:
    st.title("📝 従業員：シフト希望入力")
    staff_name = st.text_input("お名前（名字のみ推奨）")
    can_roles = st.multiselect("あなたができる役職", ["レジ", "キッチン", "ホール", "掃除"])

    st.divider()
    
    start_d = datetime.today()
    date_range = [start_d + timedelta(days=i) for i in range(7)]
    slots = generate_slots(1.0, 9, 21)
    options = ["入りたい", "足りなければ入る", "入りたくない", "絶対無理"]

    date_tabs = st.tabs([d.strftime("%m/%d(%a)") for d in date_range])
    current_answers = {}

    for i, tab in enumerate(date_tabs):
        with tab:
            day_str = date_range[i].strftime("%m/%d(%a)")
            day_df = pd.DataFrame({"時間": slots, "入りたい度": "入りたい"})
            edited_res = st.data_editor(day_df, hide_index=True, use_container_width=True, key=f"ed_{day_str}")
            current_answers[day_str] = edited_res.to_dict()

    if st.button("全日程の回答を送信する"):
        if not staff_name or not can_roles:
            st.error("入力漏れがあります。")
        else:
            # 1. 送信するデータを作成
            new_row = pd.DataFrame([{
                "名前": staff_name,
                "できる役職": ", ".join(can_roles),
                "回答内容": json.dumps(current_answers, ensure_ascii=False),
                "送信日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }])
            
            try:
                # 2. ここを修正：読み込みを挟まず、直接シートの末尾に追加する
                # worksheet="Sheet1" を指定
                conn.create(worksheet="Sheet1", data=new_row) 
                
                st.success("送信完了しました！スプレッドシートを確認してください。")
                st.balloons()
            except Exception as e:
                # 具体的なエラーを表示
                st.error(f"保存に失敗しました。以下のエラーを確認してください:\n{e}")

# --- B. 店長モード ---
else:
    # --- 安全性のためのパスワードロック ---
    admin_pw = st.sidebar.text_input("管理者パスワード", type="password")
    if admin_pw != "1234": # 好きなパスワードに変更してください
        st.info("パスワードを入力すると管理画面が表示されます。")
        st.stop()

    tab_admin, tab_staff_preview = st.tabs(["店長：設定画面", "従業員：回答状況"])
    
    with tab_admin:
        st.header("📅 シフト作成設定")
        st.write("設定を行ってください。")
        # （既存の店長設定コードをここに追加）

    with tab_staff_preview:
        st.header("📊 回答状況")
        try:
            res_df = conn.read(worksheet="Sheet1")
            st.dataframe(res_df, use_container_width=True)
        except:
            st.info("データがありません。")
