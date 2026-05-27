import os
import sys
import psycopg2
from urllib.parse import urlparse

# Load env variables
env_file = "/Users/ray/repo/Reedr1208/barkbotv0/.env.development.local"
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

db_url = os.environ.get("storage_POSTGRES_URL") or os.environ.get("STORAGE_POSTGRES_URL")
if not db_url:
    print("Error: No database connection URL found.")
    sys.exit(1)

parsed = urlparse(db_url)
# Vercel pg URLs sometimes have a query param for pgbouncer that psycopg2 might struggle with
# Or require sslmode=require
db_url = f"{parsed.scheme}://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}?sslmode=require"


ddl = """
-- 1. persona_factor_definitions
CREATE TABLE IF NOT EXISTS persona_factor_definitions (
  factor_key text primary key,
  display_name text not null,
  score_min smallint not null default 1,
  score_max smallint not null default 5,
  neutral_score smallint not null default 3,
  low_label text not null,
  high_label text not null,
  scoring_guidance_jsonb jsonb not null,
  style_rules_by_score_jsonb jsonb not null,
  active boolean not null default true,
  catalog_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. persona_archetypes
CREATE TABLE IF NOT EXISTS persona_archetypes (
  archetype_key text primary key,
  archetype_name text not null,
  archetype_family text not null,
  description text not null,
  centroid_scores_jsonb jsonb not null,
  eligibility_rules_jsonb jsonb not null default '{}'::jsonb,
  style_overrides_jsonb jsonb not null,
  variant_styles_jsonb jsonb not null,
  example_lines_jsonb jsonb not null,
  active boolean not null default true,
  catalog_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 3. animal_fact_profiles
CREATE TABLE IF NOT EXISTS animal_fact_profiles (
  animal_id text primary key references animals(animal_id),
  source_record_hash text not null,

  dog_name text not null,
  age_summary text,
  weight_summary text,
  breed_or_description text,
  sex_neuter_status text,
  location_summary text,
  location_detail text,
  adoption_url text,
  image_public_url text,

  backstory_summary text,
  important_facts_jsonb jsonb not null,
  risk_flags_jsonb jsonb not null,
  unknowns_jsonb jsonb not null,
  strengths_jsonb jsonb not null,
  challenges_jsonb jsonb not null,
  ideal_home_jsonb jsonb not null,
  management_notes_jsonb jsonb not null,

  other_animals_notes text,
  people_notes text,
  containment_notes text,
  medical_notes text,
  adoption_process_notes text,

  evidence_jsonb jsonb not null,
  schema_version text not null,
  extraction_model text not null,
  extraction_params_jsonb jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 4. animal_persona_overrides
CREATE TABLE IF NOT EXISTS animal_persona_overrides (
  animal_id text primary key references animals(animal_id),
  force_primary_archetype_key text null references persona_archetypes(archetype_key),
  force_secondary_archetype_key text null references persona_archetypes(archetype_key),
  locked_factor_scores_jsonb jsonb null,
  style_override_jsonb jsonb null,
  opening_override_line text null,
  editorial_notes text null,
  updated_by text null,
  updated_at timestamptz not null default now()
);

-- 5. animal_persona_profiles
CREATE TABLE IF NOT EXISTS animal_persona_profiles (
  animal_id text primary key references animals(animal_id),
  source_record_hash text not null,

  factor_scores_jsonb jsonb not null,
  salient_factors_jsonb jsonb not null,

  primary_archetype_key text not null references persona_archetypes(archetype_key),
  secondary_archetype_key text null references persona_archetypes(archetype_key),
  variant_key text null,

  persona_summary text not null,
  voice_rules_jsonb jsonb not null,
  style_examples_jsonb jsonb not null,
  opening_disclosure_line text not null,
  persona_guardrails_jsonb jsonb not null,

  schema_version text not null,
  scoring_model text not null,
  scoring_params_jsonb jsonb not null,
  override_applied boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 6. system_prompts_v2
CREATE TABLE IF NOT EXISTS system_prompts_v2 (
  animal_id text not null references animals(animal_id),
  prompt_version text not null,
  source_record_hash text not null,

  system_prompt text not null,
  render_context_jsonb jsonb not null,
  validation_results_jsonb jsonb not null,

  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  primary key (animal_id, prompt_version)
);
"""

print("Connecting to DB to run V2 Migrations...")
try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(ddl)
    print("Migration successful! Tables created.")
    cursor.close()
    conn.close()
except Exception as e:
    print("Error during migration:")
    print(e)
    sys.exit(1)
