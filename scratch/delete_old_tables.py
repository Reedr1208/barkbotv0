import os
import psycopg2
from pathlib import Path

def get_db_url():
    env_local = Path(__file__).resolve().parent.parent / ".env.local"
    env_dev = Path(__file__).resolve().parent.parent / ".env.development.local"
    db_url = None
    for env_file in (env_local, env_dev):
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k.strip() == "storage_POSTGRES_URL_NON_POOLING":
                            db_url = v.strip().strip('"').strip("'")
                            break
        if db_url:
            break
    if not db_url:
        db_url = os.environ.get("storage_POSTGRES_URL_NON_POOLING")
    return db_url

def main():
    db_url = get_db_url()
    if not db_url:
        print("Error: Could not find storage_POSTGRES_URL_NON_POOLING in env files.")
        return

    print("Connecting to Supabase Database...")
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Query tables starting with old_
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_name LIKE 'old_%';
    """)
    tables = [row[0] for row in cur.fetchall()]

    if not tables:
        print("No tables found starting with 'old_'.")
        cur.close()
        conn.close()
        return

    print(f"Found {len(tables)} tables starting with 'old_':")
    for t in tables:
        print(f" - {t}")

    for t in tables:
        print(f"Dropping table {t}...")
        # Safe table name quoting using psycopg2 sql utilities or standard formatting with double quotes
        cur.execute(f'DROP TABLE IF EXISTS public."{t}" CASCADE;')
        print(f"Successfully dropped {t}.")

    cur.close()
    conn.close()
    print("All done!")

if __name__ == "__main__":
    main()
