import sqlite3
conn = sqlite3.connect(r'D:\Marcus\Desktop\Andent_Webapp\data\andent_web.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
for t in cur.fetchall():
    print(t[0])
conn.close()
