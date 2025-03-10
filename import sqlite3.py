import sqlite3
import pandas as pd

# SQLite に接続
conn = sqlite3.connect("questions.db")

# 各テーブルをエクスポート
tables = ["categories", "difficulty_levels", "questions"]
for table in tables:
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    df.to_csv(f"{table}_clean.csv", index=False, quoting=2, encoding="utf-8")  # ✅ 余計な `""` をつけない！

# 接続を閉じる
conn.close()

print("✅ SQLite から `正しいCSV` をエクスポートしました！")
