#!/usr/bin/env python3
"""
Migration script: creates saved_dogs, chat_conversations, and chat_messages tables.
Run from the barkbotv0 directory: python scratch/run_migration.py
"""

import os
import sys

# Load .env.local
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env.local')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip(); val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            os.environ.setdefault(key, val)

import psycopg2

raw_url = (
    os.environ.get("storage_POSTGRES_URL") or
    os.environ.get("POSTGRES_URL") or
    os.environ.get("DATABASE_URL")
)
if not raw_url:
    print("ERROR: No POSTGRES_URL found in environment."); sys.exit(1)

# Strip query string params that psycopg2 doesn't support
conn_str = raw_url.split('?')[0]
print("Connecting to database...")

try:
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    cur = conn.cursor()
    print("Connected.")
except Exception as e:
    print(f"Connection failed: {e}"); sys.exit(1)

DDL = """
-- saved_dogs table
CREATE TABLE IF NOT EXISTS saved_dogs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email TEXT NOT NULL REFERENCES user_preferences(email) ON DELETE CASCADE,
  animal_id TEXT NOT NULL,
  dog_name TEXT,
  dog_image_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (email, animal_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_dogs_email ON saved_dogs(email);

-- chat_conversations table
CREATE TABLE IF NOT EXISTS chat_conversations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email TEXT NOT NULL REFERENCES user_preferences(email) ON DELETE CASCADE,
  animal_id TEXT NOT NULL,
  dog_name TEXT,
  dog_image_url TEXT,
  last_message_preview TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (email, animal_id)
);
CREATE INDEX IF NOT EXISTS idx_chat_conv_email ON chat_conversations(email);
CREATE INDEX IF NOT EXISTS idx_chat_conv_updated_at ON chat_conversations(updated_at DESC);

-- chat_messages table
CREATE TABLE IF NOT EXISTS chat_messages (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  conversation_id BIGINT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_msg_conversation_id ON chat_messages(conversation_id, created_at ASC);
"""

try:
    cur.execute(DDL)
    print("✅ Migration complete: saved_dogs, chat_conversations, chat_messages tables created (if not already existing).")
except Exception as e:
    print(f"❌ Migration failed: {e}")
    sys.exit(1)
finally:
    cur.close()
    conn.close()
