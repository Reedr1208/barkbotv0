import os
import sys
import psycopg2
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

sys.path.append("/Users/chayev/repos/Reedr1208/barkbotv0")
env_file = "/Users/chayev/repos/Reedr1208/barkbotv0/.env.local"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                os.environ[key] = val

db_url = os.environ.get("STORAGE_POSTGRES_URL") or os.environ.get("storage_POSTGRES_URL")
if not db_url:
    print("Error: No database connection URL found.")
    sys.exit(1)

# Let's clean the url by removing query parameters that psycopg2 doesn't understand
parsed = urlparse(db_url)
print("Parsed URL Scheme:", parsed.scheme)
print("Parsed Host:", parsed.hostname)

# Strip out query parameters
cleaned_url = urlunparse((
    parsed.scheme,
    parsed.netloc,
    parsed.path,
    parsed.params,
    "", # No query parameters
    parsed.fragment
))

try:
    print("Attempting connection with cleaned URL...")
    conn = psycopg2.connect(cleaned_url)
    print("Connection successful with cleaned URL!")
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    print("Version:", cursor.fetchone())
    cursor.close()
    conn.close()
except Exception as e1:
    print("Error with cleaned URL:", e1)
    
    # Try connecting using separate credentials
    try:
        print("Attempting connection with separate host/user/password...")
        host = os.environ.get("STORAGE_POSTGRES_HOST") or os.environ.get("storage_POSTGRES_HOST")
        user = os.environ.get("STORAGE_POSTGRES_USER") or os.environ.get("storage_POSTGRES_USER")
        password = os.environ.get("STORAGE_POSTGRES_PASSWORD") or os.environ.get("storage_POSTGRES_PASSWORD")
        database = os.environ.get("STORAGE_POSTGRES_DATABASE") or os.environ.get("storage_POSTGRES_DATABASE")
        
        conn2 = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=5432
        )
        print("Connection successful with credentials!")
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT version();")
        print("Version:", cursor2.fetchone())
        cursor2.close()
        conn2.close()
    except Exception as e2:
        print("Error with credentials:", e2)
