import streamlit as st
import pandas as pd
from datetime import time, datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import json

st.set_page_config(layout="wide", page_title="シフト最適化システム")

# --- 1. Google Sheets 接続設定 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("接続失敗。Secretsを確認してください。")
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
    
    # 【自動化ポイント】店長の設定を読み込む
    try:
        settings_df = conn.read(worksheet="Settings")
        conf = settings_df.iloc[0]
        start_d = datetime.strptime(conf["開始日"], "%Y-%m-%d")
        end_d = datetime.strptime(conf["終了日"], "%Y-%m-%d")
        # 営業時間のスロットも店長設定に合わせる
        slots = generate_slots(float(conf["時間間隔"]), int(conf["開始時"]), int(conf["終了時"]))
    except:
        # 読み込めない場合のデフォルト
        start_d = datetime.today()
        end_d = start_d + timedelta(days=6)
        slots = generate_slots(1.0, 9, 21)

    staff_name = st.text_input("お名前（名字のみ推奨）")
    can_roles = st.multiselect("あなたができる役職", ["レジ", "キッチン", "ホール", "掃除"])

    st.divider()
    
    date_range = [start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)]
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
                conn.create(worksheet="Sheet1", data=new_row)
                st.success("送信完了しました！")
                st.balloons()
            except Exception as e:
                st.error(f"保存失敗: {e}")

# --- B. 店長モード ---
else:
    admin_pw = st.sidebar.text_input("管理者パスワード", type="password")
    if admin_pw != "1234":
        st.info("パスワードを入力してください。")
        st.stop()

    tab_admin, tab_staff_preview = st.tabs(["店長：設定画面", "従業員：回答状況"])
    
    with tab_admin:
        st.sidebar.header("📅 シフト期間設定")
        start_date = st.sidebar.date_input("作成開始日", datetime.today())
        end_date = st.sidebar.date_input("作成終了日", datetime.today() + timedelta(days=7))

        st.sidebar.header("⏰ 営業時間設定")
        time_unit = st.sidebar.select_slider("刻み(時間)", options=[0.5, 1.0, 2.0], value=1.0)
        biz_range = st.sidebar.select_slider("営業時間の範囲", options=[i for i in range(37)], value=(9, 21))

        if st.sidebar.button("この設定を従業員画面に反映する"):
            settings_data = pd.DataFrame([{
                "開始日": start_date.strftime("%Y-%m-%d"),
                "終了日": end_date.strftime("%Y-%m-%d"),
                "時間間隔": time_unit,
                "開始時": biz_range[0],
                "終了時": biz_range[1]
            }])
            try:
                # Settingsシートを上書き
                conn.update(worksheet="Settings", data=settings_data)
                st.sidebar.success("反映されました！URLを共有してください。")
            except:
                st.sidebar.error("Settingsシートを作成してください。")

        st.header("🔗 共有用URL")
        staff_url = f"https://iaaaoo012-staff-shift-app.streamlit.app/?mode=staff"
        st.code(staff_url)
        st.info("上記ボタンで反映後、このURLを配れば設定した期間の入力画面になります。")

    with tab_staff_preview:
        st.header("📊 回答状況")
        try:
            res_df = conn.read(worksheet="Sheet1")
            st.dataframe(res_df, use_container_width=True)
        except:
            st.info("データがありません。")
