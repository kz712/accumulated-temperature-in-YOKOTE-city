import streamlit as st
import datetime
import pandas as pd
import numpy as np
import altair as alt
import locale
import os

# ==========================================
# 0. カレンダーの表記を日本語（数字の月）にするためのロケール設定
# ==========================================
def set_japanese_locale():
    locales = ['ja_JP.UTF-8', 'ja_JP.utf8', 'ja_JP', 'japanese']
    for loc in locales:
        try:
            locale.setlocale(locale.LC_ALL, loc)
            return
        except locale.Error:
            continue
    os.environ['LC_ALL'] = 'ja_JP.UTF-8'

set_japanese_locale()

# ページ設定
st.set_page_config(page_title="横手市 積算温度算出・予測アプリ", layout="wide")
st.title("🍏 横手市 積算温度算出・予測アプリ")
st.caption("気象庁のWebサイトから横手市の最新実況値を自動取得し、平年値と組み合わせて計算します。")

# ==========================================
# 1. 【自動参照】気象庁データ＆平年値の読み込み
# ==========================================
@st.cache_data(ttl=21600)  # 6時間キャッシュ（気象庁サーバーへの負荷軽減）
def fetch_yokote_actual_data(year):
    """気象庁のHPから横手市の日ごとの実況気温を自動取得する"""
    all_months_data = []
    current_month = datetime.date.today().month
    
    for month in range(1, current_month + 1):
        url = f"https://www.data.jma.go.jp/stats/etrn/view/daily_a1.php?prec_no=32&block_no=0313&year={year}&month={month}&day=&view=p1"
        try:
            tables = pd.read_html(url)
            df_tables = tables[0]
            
            df_cleaned = pd.DataFrame({
                "day": df_tables.iloc[:, 0],       
                "temp": df_tables.iloc[:, 4]       
            })
            
            df_cleaned = df_cleaned[pd.to_numeric(df_cleaned['day'], errors='coerce').notnull()]
            df_cleaned['day'] = df_cleaned['day'].astype(int)
            df_cleaned['temp'] = pd.to_numeric(df_cleaned['temp'], errors='coerce')
            
            df_cleaned['date'] = df_cleaned['day'].apply(lambda d: datetime.date(year, month, d))
            all_months_data.append(df_cleaned[['date', 'temp']])
        except Exception as e:
            continue
            
    if all_months_data:
        return pd.concat(all_months_data, ignore_index=True).dropna()
    else:
        return pd.DataFrame(columns=["date", "temp"])

@st.cache_data
def load_normal_data():
    """横手市の平年値シミュレーション数値"""
    normal_dates = pd.date_range(start="2026-01-01", end="2026-12-31")
    normal_temps = [11.5 - 13.5 * np.cos(2 * np.pi * (i - 25) / 365) for i in range(365)]
    df_normal = pd.DataFrame({
        "month_day": normal_dates.strftime("%m-%d"),
        "normal_temp": normal_temps
    })
    return df_normal

# データのロード
today = datetime.date.today()
with st.spinner("気象庁から最新の横手市の気温データを取得中..."):
    df_actual = fetch_yokote_actual_data(today.year)
    df_normal = load_normal_data()

# ==========================================
# 2. サイドバー設定・温度判定ロジック
# ==========================================
st.sidebar.header("⚙️ 共通設定")
st.sidebar.info(f"本日の日付: {today.strftime('%Y年%m月%d日')}")

temp_adjust = st.sidebar.slider(
    "温度補正値 (℃)", 
    min_value=-5.0, 
    max_value=10.0, 
    value=0.0, 
    step=0.5,
    help="施設内と外気温に差がある場合、一律で日平均気温に加減算します"
)

base_line_temp = st.sidebar.number_input(
    "生育限界の基準温度 (℃)", 
    min_value=0.0, 
    max_value=15.0, 
    value=0.0, 
    step=1.0,
    help="この温度以下の日は積算にカウントしません"
)

def get_daily_temp(target_date):
    if target_date <= today:
        res = df_actual[df_actual["date"] == target_date]
        if not res.empty:
            return res.iloc[0]["temp"]
    
    mm_dd = target_date.strftime("%m-%d")
    res_normal = df_normal[df_normal["month_day"] == mm_dd]
    if not res_normal.empty:
        return res_normal.iloc[0]["normal_temp"]
    return 15.0

# ==========================================
# 3. メイン画面：タブ構成
# ==========================================
tab1, tab2 = st.tabs(["📊 期間指定で積算温度を計算", "🔮 開花日から到達日を逆算"])

# --- タブ1: 期間指定計算 ---
with tab1:
    st.header("指定期間の積算温度")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("開始日", value=datetime.date(today.year, 5, 1), format="YYYY/MM/DD")
    with col2:
        end_date = st.date_input("終了日", value=today + datetime.timedelta(days=30), format="YYYY/MM/DD")
        
    if start_date > end_date:
        st.error("エラー: 開始日は終了日より前の日付を指定してください。")
    else:
        calc_date = start_date
        dates_list, temps_list, types_list, accum_list = [], [], [], []
        current_accum = 0.0
        
        while calc_date <= end_date:
            base_t = get_daily_temp(calc_date)
            adjusted_t = base_t + temp_adjust
            final_t = adjusted_t if adjusted_t > base_line_temp else 0.0
            current_accum += final_t
            
            dates_list.append(calc_date)
            temps_list.append(final_t)
            types_list.append("気象庁実況値" if calc_date <= today else "平年値（予測）")
            accum_list.append(current_accum)
            calc_date += datetime.timedelta(days=1)
            
        df_result = pd.DataFrame({
            "日付": dates_list, 
            "補正後気温(℃)": temps_list, 
            "データ種別": types_list, 
            "累積温度(℃·日)": accum_list
        })
        
        df_result_display = df_result.copy()
        df_result_display["日付"] = pd.to_datetime(df_result_display["日付"]).dt.strftime("%Y/%m/%d")
        
        st.metric(label=f"期間内の総積算温度 ({start_date.strftime('%Y/%m/%d')} 〜 {end_date.strftime('%Y/%m/%d')})", value=f"{current_accum:.1f} ℃・日")
        
        df_melted_tab1 = df_result.melt(id_vars=["日付"], value_vars=["累積温度(℃·日)"], var_name="指標", value_name="温度(℃·日)")
        chart_tab1 = alt.Chart(df_melted_tab1).mark_line().encode(
            x=alt.X("日付:T", title="日付", axis=alt.Axis(format="%m/%d")),
            y=alt.Y("温度(℃·日):Q", title="積算温度 (℃・日)"),
            color=alt.Color("指標:N")
        ).properties(width=700, height=400)
        
        st.altair_chart(chart_tab1, use_container_width=True, theme="streamlit")
        st.dataframe(df_result_display, use_container_width=True)

# --- タブ2: 到達日逆算 ---
with tab2:
    st.header("目標積算温度からの到達予想日逆算")
    col3, col4 = st.columns(2)
    with col3:
        bloom_date = st.date_input("開花日（計算開始日）", value=datetime.date(today.year, 6, 1), format="YYYY/MM/DD")
    with col4:
        target_temp = st.number_input("目標積算温度 (℃・日)", 100.0, 2000.0, 900.0, 50.0)
        
    calc_date = bloom_date
    current_accum = 0.0
    dates_list, accum_list, types_list = [], [], []
    reached_date = None
    
    # 予測日を特定するため、十分な期間（150日間）シミュレーションを実行
    for _ in range(150):
        base_t = get_daily_temp(calc_date)
        adjusted_t = base_t + temp_adjust
        final_t = adjusted_t if adjusted_t > base_line_temp else 0.0
        current_accum += final_t
        
        dates_list.append(calc_date)
        accum_list.append(current_accum)
        types_list.append("気象庁実況値" if calc_date <= today else "平年値（予測）")
        
        if current_accum >= target_temp and reached_date is None:
            reached_date = calc_date
        calc_date += datetime.timedelta(days=1)
        
    df_predict = pd.DataFrame({"日付": dates_list, "予測累積温度(℃·日)": accum_list, "データ種別": types_list})
    
    if reached_date:
        days_from_bloom = (reached_date - bloom_date).days
        days_from_today = (reached_date - today).days
        st.success(f"🎯 目標の {target_temp} ℃・日 に達するのは **{reached_date.strftime('%Y/%m/%d')}** 頃と予想されます！")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1: 
            st.metric("開花からの日数", f"{days_from_bloom} 日間")
        with col_m2: 
            st.metric("今日からの残り日数", f"あと {days_from_today} 日" if days_from_today >= 0 else "既に到達")
            
        st.subheader("目標到達までのシミュレーション曲線（予測日の前後10日間）")
        
        df_predict["目標温度"] = target_temp
        df_melted = df_predict.melt(
            id_vars=["日付"], 
            value_vars=["予測累積温度(℃·日)", "目標温度"],
            var_name="指標", 
            value_name="温度(℃·日)"
        )
        
        # 【修正点】横軸の最小値・最大値を「到達予想日の前後10日」に設定
        start_graph_date = reached_date - datetime.timedelta(days=10)
        end_graph_date = reached_date + datetime.timedelta(days=10)
        
        x_min = pd.Timestamp(start_graph_date).timestamp() * 1000
        x_max = pd.Timestamp(end_graph_date).timestamp() * 1000
        
        # 5日ごとのミリ秒換算値
        five_days_ms = 5 * 24 * 60 * 60 * 1000
        
        # 目盛（ticks）の位置を予測日を基準に5日刻み（計5箇所）で明示的に指定
        tick_values = [
            x_min,                          # 10日前
            x_min + five_days_ms,           # 5日前
            pd.Timestamp(reached_date).timestamp() * 1000, # 予測日（当日）
            x_min + three_times := (five_days_ms * 3), # 5日後
            x_max                           # 10日後
        ]
        
        y_max = float(target_temp + 200)

        # グラフ描画
        chart = alt.Chart(df_melted).mark_line().encode(
            x=alt.X(
                "日付:T", 
                title="日付", 
                scale=alt.Scale(domain=[x_min, x_max]),
                axis=alt.Axis(format="%m/%d", values=tick_values)
            ),
            y=alt.Y(
                "温度(℃·日):Q", 
                title="積算温度 (℃・日)", 
                scale=alt.Scale(domain=[0, y_max], clamp=True)
            ),
            color=alt.Color("指標:N", scale=alt.Scale(range=["#1f77b4", "#ff7f0e"]))
        ).properties(width=700, height=400)

        st.altair_chart(chart, use_container_width=True, theme="streamlit")
        
    else:
        st.warning("設定された期間内（150日以内）に目標積算温度に到達しませんでした。設定値を見直してください。")
