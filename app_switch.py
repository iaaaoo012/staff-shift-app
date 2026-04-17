import streamlit as st
import pandas as pd
from datetime import time, datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import json

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
            new_row = pd.DataFrame([{
                "名前": staff_name,
                "できる役職": ", ".join(can_roles),
                "回答内容": json.dumps(current_answers, ensure_ascii=False),
                "送信日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }])
            try:
                # 400エラー対策：createメソッドで直接追加
                conn.create(worksheet="Sheet1", data=new_row)
                st.success("送信完了しました！")
                st.balloons()
            except Exception as e:
                st.error(f"保存に失敗しました。エラー: {e}")

# --- B. 店長モード ---
else:
    # パスワードロック（1234の部分を好きな文字に変えてください）
    admin_pw = st.sidebar.text_input("管理者パスワード", type="password")
    if admin_pw != "1234":
        st.info("パスワードを入力すると管理画面が表示されます。")
        st.stop()

    tab_admin, tab_staff_preview = st.tabs(["店長：設定画面", "従業員：回答状況"])
    
    with tab_admin:
        # --- 復活：店長の設定パーツ ---
        st.sidebar.header("📅 基本設定")
        start_date = st.sidebar.date_input("作成開始日", datetime.today())
        end_date = st.sidebar.date_input("作成終了日", datetime.today() + timedelta(days=7))

        st.sidebar.header("⏰ 営業形式")
        time_mode = st.sidebar.radio("営業時間の設定方法", ["連続した時間を設定", "ブロック毎時間を設定"])
        roles = st.multiselect("必要な役職", ["レジ", "キッチン", "ホール", "掃除"], default=["レジ", "キッチン"])

        st.divider()

        if time_mode == "連続した時間を設定":
            st.header("🕒 連続時間の詳細設定")
            col1, col2 = st.columns(2)
            with col1:
                time_unit = st.select_slider("時間の間隔", options=[0.5, 1.0, 2.0], value=1.0)
            with col2:
                biz_range = st.select_slider("営業時間の範囲", options=[i for i in range(37)], value=(9, 21))
            
            slots = generate_slots(time_unit, biz_range[0], biz_range[1])
            if roles and slots:
                st.subheader("役職・時間ごとの必要人数")
                df_init = pd.DataFrame(1, index=slots, columns=roles)
                st.data_editor(df_init, use_container_width=True)

        elif time_mode == "ブロック毎時間を設定":
            st.header("🧱 ブロック毎の詳細設定")
            if 'blocks' not in st.session_state:
                st.session_state.blocks = pd.DataFrame([
                    {"ブロック名": "午前", "開始": "09:00", "終了": "12:00"},
                    {"ブロック名": "午後", "開始": "13:00", "終了": "17:00"}
                ])
            edited_blocks = st.data_editor(st.session_state.blocks, num_rows="dynamic", use_container_width=True)
            if roles:
                st.subheader("役職・ブロックごとの必要人数")
                block_names = edited_blocks["ブロック名"].tolist()
                df_block_init = pd.DataFrame(1, index=block_names, columns=roles)
                st.data_editor(df_block_init, use_container_width=True)

        st.divider()
        st.header("🧬 最適化実行")
        if st.button("最適化を開始する"):
            st.warning("従業員の回答データを読み込んでいます...")

    with tab_staff_preview:
        st.header("📊 回答状況")
        try:
            res_df = conn.read(worksheet="Sheet1")
            st.dataframe(res_df, use_container_width=True)
        except:
            st.info("データがまだありません。")
