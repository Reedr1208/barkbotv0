"""
Migration: Dog recommender agent infrastructure.

Creates (idempotent — safe to re-run):
  1. Schema `recommender` (NOT exposed via PostgREST — only `public` is).
  2. View `recommender.chattable_dogs` — one row per chat-eligible dog with
     normalized, query-friendly columns. This is the ONLY object the
     recommender LLM's SQL can read.
  3. Login role `recommender_ro`:
       - USAGE on schema recommender + SELECT on the view, nothing else
       - default_transaction_read_only = on
       - statement_timeout = 3s, connection limit 10
     The view runs with its owner's privileges, so the role needs no access
     to the underlying public tables (chat_messages, user_preferences, …).
  4. Column `public.chat_messages.recommendations jsonb` (nullable) so
     recommendation cards can be re-rendered when a chat is resumed.

Usage:
  python scripts/migrate_recommender.py            # create/update everything
  python scripts/migrate_recommender.py --verify   # only run the access checks

On first run a random password is generated for recommender_ro and the full
connection string is written to .env.local as RECOMMENDER_DATABASE_URL.
Add that same value to Railway env vars before deploying.
"""

import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse, quote

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from jobs.lib.db import load_env  # noqa: E402

import psycopg2  # noqa: E402

ROLE = "recommender_ro"

VIEW_SQL = r"""
CREATE OR REPLACE VIEW recommender.chattable_dogs AS
SELECT
  a.animal_id,
  COALESCE(NULLIF(f.dog_name, ''), a.name)                         AS name,
  CASE WHEN f.sex ILIKE 'female%' THEN 'female'
       WHEN f.sex ILIKE 'male%'   THEN 'male' END                   AS sex,
  f.age_summary,
  CASE WHEN f.age_summary ~ '\d' THEN ROUND(
         COALESCE(SUBSTRING(f.age_summary FROM '(\d+)\s*yr')::numeric, 0)
       + COALESCE(SUBSTRING(f.age_summary FROM '(\d+)\s*mo')::numeric, 0) / 12.0, 1)
  END                                                               AS age_years,
  CASE WHEN f.age_bucket ILIKE 'puppy%'  THEN 'puppy'
       WHEN f.age_bucket ILIKE 'young%'  THEN 'young'
       WHEN f.age_bucket ILIKE 'adult%'  THEN 'adult'
       WHEN f.age_bucket ILIKE 'senior%' THEN 'senior' END          AS age_group,
  f.weight_summary,
  SUBSTRING(f.weight_summary FROM '(\d+(?:\.\d+)?)\s*lb')::numeric  AS weight_lbs,
  CASE WHEN f.weight_class ILIKE 'small%'  THEN 'small'
       WHEN f.weight_class ILIKE 'medium%' THEN 'medium'
       WHEN f.weight_class ILIKE 'large%'  THEN 'large' END         AS size,
  NULLIF(NULLIF(TRIM(f.breed_or_description), ''), 'Unknown')       AS breed,
  CASE WHEN LOWER(f.energy_level) IN ('medium', 'moderate') THEN 'medium'
       WHEN LOWER(f.energy_level) IN ('high', 'calm') THEN LOWER(f.energy_level)
  END                                                               AS energy_level,
  CASE LOWER(f.good_with_dogs) WHEN 'yes' THEN 'yes' WHEN 'no' THEN 'no'
       ELSE 'unknown' END                                           AS good_with_dogs,
  CASE LOWER(f.house_trained) WHEN 'yes' THEN 'yes' WHEN 'no' THEN 'no'
       ELSE 'unknown' END                                           AS house_trained,
  CASE WHEN LOWER(f.altered_status) IN ('spayed', 'neutered') THEN 'yes'
       WHEN LOWER(f.altered_status) = 'unaltered' THEN 'no'
       ELSE 'unknown' END                                           AS spayed_neutered,
  (SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(
     CASE WHEN jsonb_typeof(f.highlights) = 'array' THEN f.highlights ELSE '[]'::jsonb END) e)
                                                                    AS highlights,
  (SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(
     CASE WHEN jsonb_typeof(f.important_facts_jsonb) = 'array' THEN f.important_facts_jsonb ELSE '[]'::jsonb END) e)
                                                                    AS important_facts,
  (SELECT string_agg(e, ', ') FROM jsonb_array_elements_text(
     CASE WHEN jsonb_typeof(f.ideal_home_jsonb) = 'array' THEN f.ideal_home_jsonb ELSE '[]'::jsonb END) e)
                                                                    AS ideal_home,
  f.intro_summary,
  f.other_animals_notes,
  f.people_notes,
  f.medical_notes,
  p.primary_archetype_key                                           AS personality_archetype,
  an.bio                                                            AS shelter_bio,
  s.shelter_id,
  s.shelter_name,
  TRIM(REGEXP_REPLACE(s.location_display_name, '[^\x20-\x7E]+', '', 'g')) AS metro
FROM public.active_dogs a
JOIN public.animal_fact_profiles    f ON f.animal_id = a.animal_id
JOIN public.animal_persona_profiles p ON p.animal_id = a.animal_id
JOIN public.shelters                s ON s.shelter_id = a.shelter_id
LEFT JOIN public.animals           an ON an.animal_id = a.animal_id
WHERE EXISTS (SELECT 1 FROM public.system_prompts_v2 sp WHERE sp.animal_id = a.animal_id);
"""


def _admin_conn():
    load_env()
    url = os.environ.get("storage_POSTGRES_URL_NON_POOLING") or os.environ.get("STORAGE_POSTGRES_URL_NON_POOLING")
    if not url:
        sys.exit("Missing storage_POSTGRES_URL_NON_POOLING in env/.env.local")
    url = re.sub(r"[?&]supa=[^&]*", "", url)
    return psycopg2.connect(url), url


def _build_role_url(admin_url: str, password: str) -> str:
    """Same pooler host as admin, but authenticate as recommender_ro.<project_ref>."""
    p = urlparse(admin_url)
    admin_user = p.username or "postgres"
    project_ref = admin_user.split(".", 1)[1] if "." in admin_user else ""
    user = f"{ROLE}.{project_ref}" if project_ref else ROLE
    port = 6543  # transaction-mode pooler — best for short, stateless queries
    return f"postgresql://{user}:{quote(password, safe='')}@{p.hostname}:{port}{p.path or '/postgres'}?sslmode=require"


def _write_env_local(key: str, value: str) -> None:
    env_path = PROJECT_ROOT / ".env.local"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f'{key}="{value}"')
    env_path.write_text("\n".join(lines) + "\n")


def migrate() -> None:
    conn, admin_url = _admin_conn()
    conn.autocommit = True
    cur = conn.cursor()

    print("1. Schema recommender …")
    cur.execute("CREATE SCHEMA IF NOT EXISTS recommender;")

    print("2. View recommender.chattable_dogs …")
    cur.execute(VIEW_SQL)
    cur.execute("REVOKE ALL ON ALL TABLES IN SCHEMA recommender FROM PUBLIC, anon, authenticated;")

    print("3. Role recommender_ro …")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
    role_exists = cur.fetchone() is not None
    existing_url = os.environ.get("RECOMMENDER_DATABASE_URL")

    if not role_exists or not existing_url:
        password = secrets.token_urlsafe(32)
        if role_exists:
            cur.execute(f"ALTER ROLE {ROLE} WITH LOGIN PASSWORD %s", (password,))
        else:
            cur.execute(f"CREATE ROLE {ROLE} WITH LOGIN NOINHERIT NOCREATEDB NOCREATEROLE PASSWORD %s", (password,))
        role_url = _build_role_url(admin_url, password)
        _write_env_local("RECOMMENDER_DATABASE_URL", role_url)
        os.environ["RECOMMENDER_DATABASE_URL"] = role_url
        print("   → wrote RECOMMENDER_DATABASE_URL to .env.local (add it to Railway before deploying)")
    else:
        print("   → role exists and RECOMMENDER_DATABASE_URL already set; keeping password")

    cur.execute(f"ALTER ROLE {ROLE} CONNECTION LIMIT 10;")
    cur.execute(f"ALTER ROLE {ROLE} SET default_transaction_read_only = on;")
    cur.execute(f"ALTER ROLE {ROLE} SET statement_timeout = '3s';")
    cur.execute(f"ALTER ROLE {ROLE} SET search_path = recommender;")
    cur.execute(f"GRANT USAGE ON SCHEMA recommender TO {ROLE};")
    cur.execute(f"GRANT SELECT ON recommender.chattable_dogs TO {ROLE};")
    # Belt and braces: make sure nothing in public is reachable
    cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE};")
    cur.execute(f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {ROLE};")
    cur.execute(f"REVOKE CREATE ON SCHEMA public FROM {ROLE};")

    print("4. Column chat_messages.recommendations …")
    cur.execute("ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS recommendations jsonb;")

    cur.execute("SELECT count(*) FROM recommender.chattable_dogs")
    print(f"   chattable_dogs rows: {cur.fetchone()[0]}")
    conn.close()


def verify() -> bool:
    load_env()
    url = os.environ.get("RECOMMENDER_DATABASE_URL")
    if not url:
        print("RECOMMENDER_DATABASE_URL not set")
        return False
    ok = True
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    def expect_ok(sql, label):
        nonlocal ok
        try:
            cur.execute(sql)
            print(f"  ✓ {label}: {cur.fetchone()}")
        except Exception as e:
            ok = False
            print(f"  ✗ {label} FAILED: {e}")

    def expect_denied(sql, label):
        nonlocal ok
        try:
            cur.execute(sql)
            ok = False
            print(f"  ✗ {label}: NOT denied (security problem!)")
        except Exception as e:
            print(f"  ✓ {label} denied: {str(e).splitlines()[0]}")

    print("Verifying recommender_ro access …")
    expect_ok("SELECT count(*) FROM recommender.chattable_dogs", "read view")
    expect_ok("SHOW default_transaction_read_only", "read-only default")
    expect_ok("SHOW statement_timeout", "statement timeout")
    for t in ("chat_messages", "chat_conversations", "user_preferences", "saved_dogs", "animals", "active_dogs"):
        expect_denied(f"SELECT 1 FROM public.{t} LIMIT 1", f"read public.{t}")
    expect_denied("CREATE TABLE recommender.x (id int)", "create table")
    expect_denied("SELECT pg_sleep(4)", "long-running query (timeout)")
    conn.close()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return ok


if __name__ == "__main__":
    if "--verify" not in sys.argv:
        migrate()
    sys.exit(0 if verify() else 1)
