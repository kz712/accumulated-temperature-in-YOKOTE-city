import streamlit as st
import datetime
import pandas as pd
import numpy as np
import altair as alt

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
    
    # 1月から現在の月までループしてデータを取得
    for month in range(1, current_month + 1):
        # 横手観測所（ prec_no=32:秋田県, block_no=0313:横手 ）
        url = f"https://www.data.jma.go.jp/stats/etrn/view/daily_a1.php?prec_no=32&block_no=0313&year={year}&month={month}&day=&view=p1"
        try:
            # HTMLから表を抽出
            tables = pd.read_html(url)
            df_tables = tables[0]
            
            # 気象庁の表構造から「日」と「平均気温」を抽出
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
            continue
            
    if all_months_data:
        return pd.concat(all_months_data, ignore_index=True).dropna()
    else:
        return pd.DataFrame(columns=["date", "temp"])

@st.cache_data
def load_normal_data():
    """
    横手市の平年値データ（1991〜2020年基準）のシミュレーション数値
    ※横手市の気候（冬は氷点下、8月ピークで25℃前後）を再現
    """
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
st.sidebar.info(f"本日の日付: {today}")

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
        return res_normal.
