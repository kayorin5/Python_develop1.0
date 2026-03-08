import pandas as pd
from datetime import datetime

# CSVファイルを読み込む
df = pd.read_csv('weather_tokyo_data.csv')

# 列名の空白を削除（必要に応じて）
df.columns = df.columns.str.strip()

# year と day から日付を作成
def create_date(year, day):
    """
    year（年）と day（月/日形式）から日付オブジェクトを作成
    """
    month, dayofmonth = map(int, day.split('/'))
    return pd.to_datetime(f"{year}-{month:02d}-{dayofmonth:02d}")

# 日付列を作成
df['date'] = df.apply(lambda row: create_date(row['year'], row['day']), axis=1)

# temperatureが負の値（括弧で表示されている値）をfloatに変換
df['temperature'] = df['temperature'].astype(str).str.replace('(', '-').str.replace(')', '').astype(float)

# 年月でグループ化して気温の平均を計算
df['year_month'] = df['date'].dt.strftime('%Y-%m')
monthly_avg = df.groupby('year_month')['temperature'].mean()

# 結果を表示
print("月ごとの平均気温:")
print("=" * 40)
for year_month, avg_temp in monthly_avg.items():
    print(f"{year_month}: {avg_temp:.2f}°C")

# 結果をCSVファイルに保存（オプション）
result_df = pd.DataFrame({
    'year_month': monthly_avg.index,
    'average_temperature': monthly_avg.values
})
result_df.to_csv('temperature_average_by_month.csv', index=False)
print("\n" + "=" * 40)
print("結果を 'temperature_average_by_month.csv' に保存しました。")
