import psycopg2, os

url = os.getenv("SUPABASE_DB_URL")

if not url:
    print("❌ SUPABASE_DB_URL not found")
    exit()

try:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT NOW();")
    print("✅ DB Connected:", cur.fetchone())
    conn.close()
except Exception as e:
    print("❌ DB Error:", e)
