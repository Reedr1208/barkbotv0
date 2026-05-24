import os
import sys
import psycopg2
from urllib.parse import urlparse, urlunparse

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

parsed = urlparse(db_url)
cleaned_url = urlunparse((
    parsed.scheme,
    parsed.netloc,
    parsed.path,
    parsed.params,
    "", # No query parameters
    parsed.fragment
))

ddl_statements = [
    # 1. saved_dogs table
    """
    create table if not exists saved_dogs (
      id bigint generated always as identity primary key,
      email text not null references user_preferences(email) on delete cascade,
      animal_id text not null references animals(animal_id) on delete cascade,
      created_at timestamptz not null default now(),
      unique (email, animal_id)
    );
    """,
    "create index if not exists idx_saved_dogs_email on saved_dogs(email);",
    
    # 2. chat_conversations table
    """
    create table if not exists chat_conversations (
      id bigint generated always as identity primary key,
      email text not null references user_preferences(email) on delete cascade,
      animal_id text not null references animals(animal_id) on delete cascade,
      last_message_preview text,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (email, animal_id)
    );
    """,
    "create index if not exists idx_chat_conv_email on chat_conversations(email);",
    "create index if not exists idx_chat_conv_updated_at on chat_conversations(updated_at desc);",
    
    # 3. chat_messages table
    """
    create table if not exists chat_messages (
      id bigint generated always as identity primary key,
      conversation_id bigint not null references chat_conversations(id) on delete cascade,
      role text not null check (role in ('user', 'assistant', 'system')),
      content text not null,
      created_at timestamptz not null default now()
    );
    """,
    "create index if not exists idx_chat_msg_conversation_id on chat_messages(conversation_id, created_at asc);"
]

try:
    print("Connecting to PostgreSQL database to execute migrations...")
    conn = psycopg2.connect(cleaned_url)
    cursor = conn.cursor()
    
    for i, ddl in enumerate(ddl_statements, 1):
        print(f"Executing DDL statement {i}...")
        cursor.execute(ddl)
    
    conn.commit()
    print("Migrations committed successfully! New tables created successfully.")
    
    # Verify tables
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    tables = [t[0] for t in cursor.fetchall()]
    print("Active tables in 'public' schema:", tables)
    
    cursor.close()
    conn.close()
except Exception as e:
    print("Migration failed with error:", e)
    sys.exit(1)
