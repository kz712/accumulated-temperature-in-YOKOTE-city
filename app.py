import streamlit as st
import datetime
import pandas as pd
import numpy as np

# ページ設定
st.set_page_config(page_title="横手市 積算温度算出・予測アプリ", layout="wide")
st.title("🍏 横手市 積算温度算出・予測アプリ（気象庁データ自動連動）")
st.caption("気象庁のWebサイトから横手市の最新実況値を自動取得し、平年値と組み合わせて計算します。")

# ==========================================
# 1. 【自動参照】気象庁データ＆平年値の読み込み
# ==========================================
@st.cache_data(ttl=21600)  # 6時間キャッシュ（1日に何度も気象庁にアクセスするのを防ぐ）
def fetch_yokote_actual_data(year):
    """気象庁のHPから横手市の日ごとの実況気温を自動取得する"""
    all_months_data = []
    current_month = datetime.date.today().month
    
    # 1月から現在の月までループしてデータを取得
    for month in range(1, current_month + 1):
        # 横手観測所（ prec_no=32:秋田県, block_no=0313:横手 ）
        url = f"https://www.data.jma.go.jp/stats/etrn/view/daily_a1.php?prec_no=32&block_no=0313&year={year}&month={month}&day=&view=p1"
        try:
            # HTMLから表を抽出
            tables = pd.read_html(url)
            df_tables = tables[0]
            
            # 気象庁の表構造から「日」と「平均気温」を抽出
            # 階層ヘッダーになっているため調整
            df_cleaned = pd.DataFrame({
                "day": df_tables.iloc[:, 0],       # 1列目：日
                "temp": df_tables.iloc[:, 4]       # 5列目：日平均気温
            })
            
            # ヘッダー行や数値化できない行を除外
            df_cleaned = df_cleaned[pd.to_numeric(df_cleaned['day'], errors='coerce').notnull()]
            df_cleaned['day'] = df_cleaned['day'].astype(int)
            df_cleaned['temp'] = pd.to_numeric(df_cleaned['temp'], errors='coerce')
            
            # 日付型に変換
            df_cleaned['date'] = df_cleaned['day'].apply(lambda d: datetime.date(year, month, d))
            all_months_data.append(df_cleaned[['date', 'temp']])
        except Exception as e:
            # 未来の月やエラー時はスキップ
            continue
            
    if all_months_data:
        return pd.concat(all_months_data, ignore_index=True).dropna()
    else:
        # 万が一取得失敗した時のための最低限のバックアップ
        return pd.DataFrame(columns=["date", "temp"])

@st.cache_data
def load_normal_data():
    """
    横手市の平年値データ（1991〜2020年基準）
    ※本来はCSVから読み込むか、完全な365日分を持ちますが、
    ここではアプリ単体で動くよう横手市の傾向に合わせた簡易的な平年値数式を生成しています。
    """
    normal_dates = pd.date_range(start="2026-01-01", end="2026-12-31")
    # 横手市の平年値（冬は氷点下、8月ピークで25℃前後）を再現したサインカーブ
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
# 2. サイドバー設定・ロジック（変更なし）
# ==========================================
st.sidebar.header("⚙️ 共通設定")
st.sidebar.info(f"本日の日付: {today}")

temp_adjust = st.sidebar.slider("温度補正値 (℃)", -5.0, 10.0, 0.0, 0.5, help="施設内の温度差補正")
base_line_temp = st.sidebar.number_input("生育限界の基準温度 (℃)", 0.0, 15.0, 0.0, 1.0)

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
# 3. メイン画面：タブ構成（変更なし）
# ==========================================
tab1, tab2 = st.tabs(["📊 期間指定で積算温度を計算", "🔮 開花日から到達日を逆算"])

with tab1:
    st.header("指定期間の積算温度")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("開始日", value=datetime.date(today.year, 5, 1))
    with col2:
        end_date = st.date_input("終了日", value=today + datetime.timedelta(days=30))
        
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
            
        df_result = pd.DataFrame({"日付": dates_list, "補正後気温(℃)": temps_list, "データ種別": types_list, "累積温度(℃·日)": accum_list})
        st.metric(label=f"期間内の総積算温度 ({start_date} 〜 {end_date})", value=f"{current_accum:.1f} ℃・日")
        st.line_chart(df_result, x="日付", y="累積温度(℃·日)")
        st.dataframe(df_result, use_container_width=True)

with tab2:
    st.header("目標積算温度からの到達予想日逆算")
    col3, col4 = st.columns(2)
    with col3:
        bloom_date = st.date_input("開花日（計算開始日）", value=datetime.date(today.year, 6, 1))
    with col4:
        target_temp = st.number_input("目標積算温度 (℃・日)", 100.0, 2000.0, 900.0, 50.0)
        
    calc_date = bloom_date
    current_accum = 0.0
    dates_list, accum_list, types_list = [], [], []
    reached_date = None
    
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
        st.success(f"🎯 目標の {target_temp} ℃・日 に達するのは **{reached_date}** 頃と予想されます！")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1: st.metric("開花からの日数", f"{days_from_bloom} 日間")
        with col_m2: st.metric("今日からの残り日数", f"あと {days_from_today} 日" if days_from_today >= 0 else "既に到達")
        df_predict["目標温度"] = target_temp
        st.line_chart(df_predict, x="日付", y=["予測累積温度(℃·日)", "目標温度"])
    else:
        st.warning("設定された期間内に目標積算温度に到達しませんでした。")
