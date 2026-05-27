import os
import sys
import json
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
db_url = f"{parsed.scheme}://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}?sslmode=require"

try:
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    # Load factor definitions
    with open("WorkingFiles/persona_factor_definitions.json", "r") as f:
        factors = json.load(f)

    # Insert factor definitions
    cursor.execute("TRUNCATE TABLE persona_factor_definitions CASCADE;")
    for factor in factors:
        cursor.execute(
            """
            INSERT INTO persona_factor_definitions
            (factor_key, display_name, score_min, score_max, neutral_score, low_label, high_label, scoring_guidance_jsonb, style_rules_by_score_jsonb, active, catalog_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                factor["factor_key"],
                factor["display_name"],
                factor["score_min"],
                factor["score_max"],
                factor["neutral_score"],
                factor["low_label"],
                factor["high_label"],
                json.dumps(factor["scoring_guidance_jsonb"]),
                json.dumps(factor["style_rules_by_score_jsonb"]),
                factor["active"],
                factor["catalog_version"]
            )
        )
    print(f"Inserted {len(factors)} factor definitions.")

    # Load archetypes
    with open("WorkingFiles/persona_archetypes.json", "r") as f:
        archetypes = json.load(f)

    # Insert archetypes
    cursor.execute("TRUNCATE TABLE persona_archetypes CASCADE;")
    for arch in archetypes:
        cursor.execute(
            """
            INSERT INTO persona_archetypes
            (archetype_key, archetype_name, archetype_family, description, centroid_scores_jsonb, style_overrides_jsonb, variant_styles_jsonb, example_lines_jsonb, active, catalog_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                arch["archetype_key"],
                arch["archetype_name"],
                arch["archetype_family"],
                arch["description"],
                json.dumps(arch["centroid_scores_jsonb"]),
                json.dumps(arch["style_overrides_jsonb"]),
                json.dumps(arch["variant_styles_jsonb"]),
                json.dumps(arch["example_lines_jsonb"]),
                arch["active"],
                arch["catalog_version"]
            )
        )
    print(f"Inserted {len(archetypes)} archetypes.")

    conn.commit()
    cursor.close()
    conn.close()
    print("Seeding successful!")
except Exception as e:
    print("Error during seeding:")
    print(e)
    sys.exit(1)
