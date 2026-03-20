import psycopg2

conn = psycopg2.connect(
    host="pg",
    port=5432,
    database="pg",
    user="pg",
    password="changeme"
)
cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
tables = cur.fetchall()
print(f"Tables : {len(tables)}")
for t in tables:
    print(f"  {t[0]}")
conn.close()