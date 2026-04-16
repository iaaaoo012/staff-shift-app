import streamlit as st
import pandas as pd
from datetime import time, datetime, timedelta
from streamlit_gsheets import GSheetsConnection

# ページ設定
st.set_page_config(layout="wide", page_title="シフト最適化システム")

# --- 1. Google Sheets 接続設定 ---
# 接続エラーでアプリが停止しないよう保護
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Googleスプレッドシートへの接続に失敗しました。Secretsの設定を確認してください。")
    st.stop()

# --- 2. URLパラメータによる画面切り替え判定 ---
# 最新のStreamlit仕様(st.query_params)を使用
query_params = st.query_params
is_staff_mode = query_params.get("mode") == "staff"

# --- 3. 共通関数：時間スロット生成 ---
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

# --- A. 従業員専用モード (?mode=staff の場合) ---
if is_staff_mode:
    st.title("📝 従業員：シフト希望入力")
    st.info("店長から共有された専用画面です。")

    col_n1, col_n2 = st.columns(2)
    with col_n1:
        staff_name = st.text_input("お名前", key="staff_name_input")
    with col_n2:
        can_roles = st.multiselect("あなたができる役職", ["レジ", "キッチン", "ホール", "掃除"], key="staff_roles")

    st.divider()

    st.subheader("希望日程・時間の入力")
    st.info("点数：入りたい(100) / 足りなきゃ(30) / 入れない(-30) / 絶対無理(-100)")

    # 仮の日程（今日から1週間分）
    start_d = datetime.today()
    end_d = start_d + timedelta(days=6)
    date_range = [start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)]
    
    # 時間スロット（デフォルト 9:00-21:00）
    slots = generate_slots(1.0, 9, 21)

    date_tabs = st.tabs([d.strftime("%m/%d(%a)") for d in date_range])
    current_answers = {}
    options = ["入りたい", "足りなければ入る", "入りたくない", "絶対無理"]

    for i, tab in enumerate(date_tabs):
        with tab:
            day_str = date_range[i].strftime("%m/%d(%a)")
            day_df = pd.DataFrame({"時間": slots, "入りたい度": "入りたい"})
            edited_res = st.data_editor(
                day_df,
                column_config={"入りたい度": st.column_config.SelectboxColumn("入りたい度", options=options, required=True)},
                hide_index=True,
                use_container_width=True,
                key=f"ed_{day_str}"
            )
            current_answers[day_str] = edited_res.to_dict()

    if st.button("全日程の回答を送信する"):
        if not staff_name or not can_roles:
            st.error("お名前とできる役職を入力してください。")
        else:
            new_row = pd.DataFrame([{
                "名前": staff_name,
                "できる役職": ", ".join(can_roles),
                "回答内容": str(current_answers),
                "送信日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }])
            try:
                # 既存データを読み込んで結合
                existing_data = conn.read(worksheet="Sheet1")
                updated_df = pd.concat([existing_data, new_row], ignore_index=True)
                conn.update(worksheet="Sheet1", data=updated_df)
                st.success(f"送信完了しました。ありがとうございました！")
                st.balloons()
            except Exception as e:
                # エラー内容を具体的に表示
                st.error(f"保存に失敗しました。スプレッドシートの権限またはSecretsの設定を確認してください。エラー: {e}")

# --- B. 店長モード (通常のURLの場合) ---
else:
    tab_admin, tab_staff_preview = st.tabs(["店長：設定画面", "従業員：回答状況"])

    with tab_admin:
        st.sidebar.header("📅 基本設定")
        start_date = st.sidebar.date_input("作成開始日", datetime.today())
        end_date = st.sidebar.date_input("作成終了日", datetime.today() + timedelta(days=7))

        st.sidebar.header("⏰ 営業形式")
        time_mode = st.sidebar.radio("営業時間の設定方法", ["連続した時間を設定", "ブロック毎時間を設定"])
        roles = st.multiselect("必要な役職", ["レジ", "キッチン", "ホール", "掃除"], default=["レジ", "キッチン"])

        st.divider()

        slots = []
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
        st.header("🔗 従業員アンケートの共有")
        # 自分のアプリの実際のURLに合わせてここを修正してください
        staff_url = "https://iaaaoo012-staff-shift-app.streamlit.app/?mode=staff" 
        st.write("以下のURLをコピーして従業員に送ってください：")
        st.code(f"{actual_url}?mode=staff")

        st.header("🧬 最適化ロジック")
        avoid_gap = st.toggle("空き時間を作らない")
        if st.button("最適化を開始する"):
            st.warning("従業員の回答データを読み込んでいます...")

    with tab_staff_preview:
        st.header("📊 スプレッドシートからの回答状況")
        try:
            res_df = conn.read(worksheet="Sheet1")
            st.dataframe(res_df, use_container_width=True)
        except Exception:
            st.info("回答データがまだありません。")
