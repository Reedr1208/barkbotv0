import re

with open("jobs/06_scrape_nycacc_inventory.py", "r") as f:
    content = f.read()

# Add imports
imports_addition = """
import os
from supabase import create_client

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_supabase_client():
    from pathlib import Path
    env_local = Path(__file__).resolve().parent.parent / ".env.local"
    env_dev = Path(__file__).resolve().parent.parent / ".env.development.local"
    for env_file in (env_local, env_dev):
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        os.environ[k] = v.strip().strip('"').strip("'")
                        
    try:
        supabase_url = os.environ["storage_SUPABASE_URL"]
        supabase_key = os.environ["storage_SUPABASE_SERVICE_ROLE_KEY"]
        return create_client(supabase_url, supabase_key)
    except KeyError as exc:
        raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc

def record_run_start(client, triggered_by: str) -> int:
    payload = {
        "triggered_by": triggered_by,
        "source_count": 0,
        "started_at": now_iso(),
        "status": "running",
    }
    row = client.table("scrape_runs").insert(payload).execute().data[0]
    return row["id"]

def record_run_finish(client, run_id: int, status: str, notes_dict: dict) -> None:
    payload = {
        "status": status,
        "notes": json.dumps(notes_dict),
        "finished_at": now_iso(),
    }
    client.table("scrape_runs").update(payload).eq("id", run_id).execute()
"""
content = re.sub(
    r"(from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError)",
    r"\1\n" + imports_addition,
    content
)

# Modify main_async start
main_start_target = """async def main_async(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)"""

main_start_replacement = """async def main_async(args: argparse.Namespace) -> int:
    client = get_supabase_client()
    run_id = record_run_start(client, "cron_nycacc_inventory")
    status = "success"

    if "VERCEL" in os.environ or "storage_SUPABASE_URL" in os.environ:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/ms-playwright"
        os.system("python -m playwright install chromium")

    out_path = Path(args.out)
    debug_dir = Path(args.debug_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)"""

content = content.replace(main_start_target, main_start_replacement)

# Modify main_async end
main_end_target = """    rows = list(records.values())
    rows.sort(key=lambda r: int(r["animal_id"]) if r.get("animal_id", "").isdigit() else 999999999)

    write_csv(out_path, rows)

    print(f"\\nWrote {len(rows)} dog rows to {out_path.resolve()}")
    print(f"Debug folder: {debug_dir.resolve()}")

    if len(rows) == 0:
        print("\\nNo dog rows were parsed. Please send these files back for the next adjustment:")
        print(f"  {debug_dir / 'nycacc_api_logs.json'}")
        print(f"  {debug_dir / 'nycacc_graphql_logs.json'}")
        print(f"  {debug_dir / 'last_page.png'}")
        print("\\nUseful alternate run:")
        print(f"  python {Path(sys.argv[0]).name} --headed --skip-dog-filter --include-unknown-species --out {out_path}")

    return 0"""

main_end_replacement = """    rows = list(records.values())
    rows.sort(key=lambda r: int(r["animal_id"]) if r.get("animal_id", "").isdigit() else 999999999)

    print(f"\\nFound {len(rows)} dog rows.")
    print(f"Debug folder: {debug_dir.resolve()}")

    if len(rows) == 0:
        print("\\nNo dog rows were parsed. Please send these files back for the next adjustment:")
        print(f"  {debug_dir / 'nycacc_api_logs.json'}")
        print(f"  {debug_dir / 'nycacc_graphql_logs.json'}")
        print(f"  {debug_dir / 'last_page.png'}")
        print("\\nUseful alternate run:")
        print(f"  python {Path(sys.argv[0]).name} --headed --skip-dog-filter --include-unknown-species --out {out_path}")
        status = "failed"
    else:
        # Map to active_dogs format
        # animal_id, name, gender, age, weight, scraped_at, shelter_id
        db_rows = []
        for r in rows:
            db_rows.append({
                "animal_id": f"nycacc-{r.get('animal_id')}",
                "name": r.get("name"),
                "gender": r.get("gender"),
                "age": r.get("age"),
                "weight": r.get("weight"),
                "scraped_at": now_iso(),
                "shelter_id": "NYCACC",
            })
            
        print("Performing full replace of NYCACC dogs in active_dogs...")
        # Delete existing NYCACC dogs
        try:
            client.table("active_dogs").delete().eq("shelter_id", "NYCACC").execute()
            # Insert new dogs in chunks
            for chunk_start in range(0, len(db_rows), 100):
                chunk = db_rows[chunk_start:chunk_start + 100]
                client.table("active_dogs").insert(chunk).execute()
        except Exception as e:
            print(f"Error saving to db: {e}")
            status = "failed"

    notes = {"scraped_count": len(rows)}
    record_run_finish(client, run_id, status, notes)
    return 0"""

content = content.replace(main_end_target, main_end_replacement)

with open("jobs/06_scrape_nycacc_inventory.py", "w") as f:
    f.write(content)
