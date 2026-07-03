"""
Migration: Suggested Prompts Overhaul
--------------------------------------
Creates:
  - suggested_prompts table (seeded with Informative + Whimsical prompts)
  - sugg_specific text[] column on animal_fact_profiles
  - sugg_prompts text[] and chosen_prompt text columns on chat_messages

Uses direct Postgres connection via psycopg2 for DDL, then Supabase client for seed data.
"""

import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Load env
env_file = Path(__file__).resolve().parent.parent.parent / ".env.development.local"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

# ── Connect via psycopg2 for DDL ────────────────────────────────────────────
import psycopg2

# Use the non-pooling URL for DDL operations
pg_url = os.environ.get("storage_POSTGRES_URL_NON_POOLING")
if not pg_url:
    logging.error("Missing storage_POSTGRES_URL_NON_POOLING env var.")
    sys.exit(1)

logging.info(f"Connecting to Postgres...")
conn = psycopg2.connect(pg_url)
conn.autocommit = True
cur = conn.cursor()

# ── 1. Create suggested_prompts table ───────────────────────────────────────
logging.info("Creating suggested_prompts table...")
cur.execute("""
    CREATE TABLE IF NOT EXISTS suggested_prompts (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        category text NOT NULL CHECK (category IN ('Informative', 'Whimsical')),
        prompt_text text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    );
""")
logging.info("  ✓ suggested_prompts table created (or already exists).")

# ── 2. Seed suggested_prompts ───────────────────────────────────────────────
logging.info("Seeding suggested_prompts...")

INFORMATIVE_PROMPTS = [
    "What's your rescue story?",
    "Are you good with other dogs or cats?",
    "Are you good with kids or strangers?",
    "Do you have any medical needs?",
    "What should my human know?",
    "What makes you unique?",
    "What are your strengths?",
    "What does your ideal home look like?",
    "What is your energy level?",
    "What is your adoption process?",
]

WHIMSICAL_PROMPTS = [
    "What would your business card say?",
    "What's your life motto?",
    "What would you do if we joined a circus?",
    "What superpower would you choose?",
    "What fictional character do you relate to?",
    "What's your first decree as mayor?",
    "Who is your dog hero?",
]

cur.execute("SELECT COUNT(*) FROM suggested_prompts")
count = cur.fetchone()[0]
if count > 0:
    logging.info(f"  suggested_prompts already has {count} rows — skipping seed.")
else:
    for text in INFORMATIVE_PROMPTS:
        cur.execute("INSERT INTO suggested_prompts (category, prompt_text) VALUES (%s, %s)", ("Informative", text))
    for text in WHIMSICAL_PROMPTS:
        cur.execute("INSERT INTO suggested_prompts (category, prompt_text) VALUES (%s, %s)", ("Whimsical", text))
    logging.info(f"  ✓ Seeded {len(INFORMATIVE_PROMPTS) + len(WHIMSICAL_PROMPTS)} prompts ({len(INFORMATIVE_PROMPTS)} Informative, {len(WHIMSICAL_PROMPTS)} Whimsical).")

# ── 3. Add sugg_specific column to animal_fact_profiles ─────────────────────
logging.info("Adding sugg_specific column to animal_fact_profiles...")
cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'animal_fact_profiles' AND column_name = 'sugg_specific'
        ) THEN
            ALTER TABLE animal_fact_profiles ADD COLUMN sugg_specific text[];
        END IF;
    END $$;
""")
logging.info("  ✓ sugg_specific column added (or already exists).")

# ── 4. Add sugg_prompts and chosen_prompt columns to chat_messages ──────────
logging.info("Adding sugg_prompts and chosen_prompt columns to chat_messages...")
cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'chat_messages' AND column_name = 'sugg_prompts'
        ) THEN
            ALTER TABLE chat_messages ADD COLUMN sugg_prompts text[];
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'chat_messages' AND column_name = 'chosen_prompt'
        ) THEN
            ALTER TABLE chat_messages ADD COLUMN chosen_prompt text;
        END IF;
    END $$;
""")
logging.info("  ✓ sugg_prompts and chosen_prompt columns added (or already exists).")

cur.close()
conn.close()
logging.info("Migration complete! ✓")
