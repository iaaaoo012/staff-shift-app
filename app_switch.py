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
