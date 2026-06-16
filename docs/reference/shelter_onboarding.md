# Shelter Onboarding Procedure

> [!IMPORTANT]
> This document is the canonical reference for onboarding a new shelter into BarkBot.
> It is optimized for autonomous AI agent execution.

## Required Inputs

| Input | Example | Notes |
|-------|---------|-------|
| Shelter Inventory URL | `https://phillypaws.org/adopt/dogs/` | The page listing all adoptable dogs |
| Shelter Location | `Philadelphia, PA` | City, State |
| Shelter Name | `Philly PAWS` | Human-readable display name |
| Location Name | `Philadelphia, PA` | For `location_name` column |
| Shelter Acronym | `PHP` | Unique ID for `shelter_id`. Format animal_id as `{ACRONYM}-{internal_id}` |

---

## Phase 1: Site Reconnaissance

**Goal:** Understand the shelter website's structure to determine the scraping strategy.

1. Visit the inventory URL in the browser and take screenshots
2. Determine the rendering technology:
   - Static HTML (BeautifulSoup only) — preferred
   - JavaScript-rendered (needs Playwright) — acceptable
   - Shelterluv embed (iframe) — common pattern, see below
   - API-backed (fetch JSON directly) — ideal
3. Identify the animal ID pattern (e.g., `PHLP-A-181074`)
4. Identify the profile URL pattern (e.g., `https://new.shelterluv.com/embed/animal/PHLP-A-181074`)
5. Check for pagination (load-more buttons, page parameters, infinite scroll)
6. Determine if Playwright is needed — dictates Vercel cron vs GitHub Action

### Shelterluv Sites (Common Pattern)

Many shelters use Shelterluv embeds. Key identifiers:
- iframe pointing to `new.shelterluv.com`
- Animal IDs like `XXXX-A-######`
- Profile data embedded as JSON in `:animal` attribute of `<iframe-animal>` tag
- Image URLs on `new-s3.shelterluv.com`

For Shelterluv sites:
- **Inventory** requires Playwright (JS-rendered iframe) → GitHub Action
- **Profiles** can use simple HTTP requests (data in HTML)

---

## Phase 2: Database Setup

Insert into the `shelters` table via Supabase client:

```python
from jobs.lib.db import get_supabase_client
client = get_supabase_client()
client.table("shelters").insert({
    "shelter_id": "{ACRONYM}",
    "shelter_name": "{Shelter Name}",
    "city": "{City}",
    "state": "{State}",
    "location_name": "{City}, {State}",
    "location_display_name": "{City}, {State} {emoji}",
    "relative_path": "/{url_slug}"
}).execute()
```

**Emoji conventions:**
Tucson 🌵, NYC 🗽, LA 🌴, Chicago 🫘, Houston 🤠, Newark ✈️

---

## Phase 3: Create Scraper Modules

### Directory Structure
```
jobs/shelters/{acronym_lower}/
├── __init__.py
├── inventory.py
└── profiles.py
```

### Inventory Scraper
- Import from `jobs.lib.db`: `now_iso`, `get_supabase_client`
- Output fields: animal_id, name, gender, age, weight, city, state, shelter_name, shelter_profile_url, scraped_at, shelter_id
- Use full-replace save pattern with safety threshold
- If Playwright needed → must be GitHub Action

### Profile Scraper
- Use `jobs.lib.profiles_runner.run_profiles_scrape` for the main loop
- Implement `fetch_record(url, target) -> dict` with shelter-specific extraction
- Bio field is catch-all for dog-specific info. Raw text OK — normalization happens later.

---

## Phase 4: Create Legacy Wrappers

Create thin wrappers in `jobs/` with `sys.path.insert`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jobs.shelters.{acronym_lower}.inventory import main
```

---

## Phase 5: Create API Proxies + Cron Config

- Create `api/{acronym_lower}_inventory.py` and `api/{acronym_lower}_profiles.py` following existing patterns
- Add cron entries to `vercel.json`:
  - Inventory: `0 */4 * * *` (every 4 hours)
  - Profiles: `{minute_offset} * * * *` (every hour, unique offset)
- For Playwright jobs, create GitHub Actions workflow instead

---

## Phase 6: Generate Prompts Integration

Add bio_length threshold in `api/generate_prompts.py` (~line 98-116):
```python
elif s_id_upper == "{ACRONYM}":
    if bio_len < {threshold} and desc_len < {threshold}:
        continue
```

**Threshold rules:** Min 500, max 1500. Set so ≥20 dogs are eligible.

---

## Phase 7: Data Backfill + Deploy

1. Run inventory scraper → populates active_dogs
2. Run profile scraper 2-3x → populates animals
3. Calibrate bio_length threshold
4. Run generate_prompts
5. Restrict new location to reedr1208@gmail.com initially
6. Deploy, test, get user approval, then remove restriction

---

## File Checklist

- [ ] `jobs/shelters/{acronym_lower}/__init__.py`
- [ ] `jobs/shelters/{acronym_lower}/inventory.py`
- [ ] `jobs/shelters/{acronym_lower}/profiles.py`
- [ ] `jobs/{acronym_lower}_inventory.py` (legacy wrapper)
- [ ] `jobs/{acronym_lower}_profiles.py` (legacy wrapper)
- [ ] `api/{acronym_lower}_inventory.py` (API proxy)
- [ ] `api/{acronym_lower}_profiles.py` (API proxy)
- [ ] `vercel.json` (add cron entries)
- [ ] `api/generate_prompts.py` (add bio threshold)
- [ ] `shelters` table (insert record)
- [ ] `.github/workflows/` (if Playwright needed)
