# Shelter Onboarding Procedure

> [!IMPORTANT]
> This document is the canonical reference for onboarding a new shelter into ChattyHound (BarkBot).
> It reflects the **Railway** architecture (single FastAPI process + in-process APScheduler).
> Anything mentioning Vercel crons, `vercel.json`, `api/*_inventory.py` proxies, legacy
> `jobs/{x}_inventory.py` wrappers, GitHub Actions or `api/generate_prompts.py` is obsolete.

## Required Inputs

| Input | Example | Notes |
|-------|---------|-------|
| Shelter inventory URL | `https://pawsco.org/adopt` | Page listing all adoptable dogs |
| Shelter name | `PawsCo` | Human-readable; stored on every `active_dogs` / `animals` row |
| City / State | `Denver`, `CO` | |
| Location display name | `Denver, CO 🏔️` | Shown in the location picker. Reuse an existing one if the shelter shares a metro |
| URL slug | `/denver` | `shelters.relative_path`; reuse the metro's slug if it already exists |
| Shelter acronym | `PAWSCO` | Unique `shelter_id`. `animal_id = {ACRONYM}-{stable internal id}`. Must not be a prefix of another ID used in `LIKE '{ID}-%'` queries |
| Bio-length threshold | `1000` | Below this a dog gets the generic "limited info" persona (see Phase 5) |
| Official website | `https://pawsco.org/` | `shelters.website_url`. The shelter's OWN homepage (not a 24petconnect/shelterluv/adoptapet listing host). The daily `shelter_process_details` job researches adoption fees/process/contact on this domain for the chat `find_shelter_info` tool |

---

## Phase 1: Site Reconnaissance

**Goal:** pick the cheapest reliable scraping strategy and a **stable** animal ID.

1. Fetch the inventory page with `requests` (browser UA + `Accept`/`Accept-Language` headers). Save the HTML to a scratch folder.
2. Identify the technology, in order of preference:
   - JSON API (RescueGroups, Shelterluv v3, Petango, WordPress REST) — ideal
   - Server-rendered HTML (BeautifulSoup) — preferred
   - Shelterluv embed / JS SPA → Playwright (works on Railway — Chromium is in the Docker image — but is the least reliable class of scraper; ~25% failure rate historically)
3. Identify a **stable** per-dog ID. Prefer the shelter's own ID; otherwise a CMS post ID. Avoid name slugs (they get reused when a new dog has the same name).
4. Identify the profile URL pattern, pagination, and how dogs are distinguished from cats/other species.
5. Check for rate limiting / bot protection (Cloudflare `429`/`403`). If present, throttle requests and avoid per-dog requests in the inventory job.
6. Fetch 3–5 profile pages; label formats are often hand-typed and inconsistent between dogs.

### Shelterluv sites (common pattern)
- iframe pointing to `new.shelterluv.com`, IDs like `XXXX-A-######`
- Profile JSON embedded in the `:animal` attribute of `<iframe-animal>`
- Inventory usually needs Playwright; profiles can use plain HTTP

### Shelterluv v1 API with a public key (e.g. Bideawee / `BDW`)
- Some sites (often WordPress themes) render their grid client-side by calling
  `https://www.shelterluv.com/api/v1/animals?status_type=publishable` with an `X-Api-Key`
  header that's in their public JS. Search the theme JS for `shelterluv.com/api` / `X-Api-Key`.
- That's the best case: one JSON request for inventory, `GET /api/v1/animals/{Internal-ID}` per profile, no Playwright.
  Filter on `Type == "Dog"` (the feed includes cats). Honour any site-side hide rules too (Bideawee hides the `Adopted for Gallery` attribute).
- Build the bio from the structured fields (breed/sex/age/weight/size/location/published `Attributes`/`AdoptionFeeGroup`) plus the `Description` HTML with repeated adoption-process sentences removed.
  See `jobs/shelters/bdw/`.

---

## Phase 2: Scraper Modules

```
jobs/shelters/{acronym_lower}/
├── __init__.py
├── inventory.py   # → active_dogs (full replace per shelter)
└── profiles.py    # → animals (via jobs.lib.profiles_runner)
```

### Inventory (`inventory.py`)
- Entry point: `scrape_inventory()` (registry `call: "scrape_inventory"`) or `main()` (`call: "main"`). Must not require CLI args (argv is reset by the runner).
- Output rows: `animal_id, name, gender, age, weight, city, state, shelter_name, shelter_profile_url, scraped_at, shelter_id`.
  Use `Male`/`Female` for `gender` when known (the gender filter does substring matching).
- Write pattern: `DELETE active_dogs WHERE shelter_id = X` then chunked `INSERT` (100/batch).
- **Always add a zero-row guard** (raise before deleting if the parse returns 0 / implausibly few dogs) — otherwise a markup change wipes the shelter and the cleanup job can cascade-delete favorites and chats.
- Record runs with `record_run_start(client, "cron_{acronym_lower}_inventory")` / `record_run_finish`.

### Profiles (`profiles.py`)
- Implement `fetch_record(url, target) -> dict` and call `run_profiles_scrape(shelter_id=..., fetch_record_fn=...)` from `main()`.
- Return keys: `shelter_profile_url, animal_id, shelter_name, name, gender, age, weight, more_info, bio, shelter_image_url, image_file (None), image_public_url (None), city, state, shelter_id`.
- `bio` is the catch-all for dog-specific text (raw labelled text is fine — fact extraction normalizes it). Drop site boilerplate.
- Raise `ValueError("NOT_A_DOG")` for non-dogs (runner deletes them from all tables).
- Pass `on_http_error` to drop dogs from `active_dogs` on `404/410` (adopted/unpublished). Don't delete on `403/429/5xx`.
- Tune `dogs_per_run` (default 30) and `default_sleep` for rate-limited sites. Note: the `SCRAPE_SLEEP_SECONDS` env var overrides `default_sleep` globally, so enforce site-specific throttling inside the module if it matters.
- Combined inventory+profile jobs (MP, WWLA pattern) are discouraged: they bypass the runner's targeting, hashing and 404 handling.

### Validate before touching the DB
Dry-run the parsers locally (no writes) against the live site; check names, gender, age, weight, image URL and bio for every dog, and QA a few against the browser.

---

## Phase 3: Wire Into the App (code)

| File | Change |
|---|---|
| `jobs/shelter_registry.py` | Add `{acronym}_inventory` (cron `M */4 * * *`) and `{acronym}_profiles` (cron `M * * * *`) to `SHELTER_JOBS`. Pick minutes that aren't already crowded. This is what APScheduler on Railway runs, and what `/admin/crons` and `POST /api/cron/{job_id}` see. |
| `jobs/lib/enrichment.py` | Add the shelter to `_BIO_MIN_LENGTH` (key must equal the live `shelter_id`). |
| `routes/admin_routes.py` | Add to `SHELTER_INVENTORY_JOBS` and `SHELTER_PROFILES_JOBS` (Admin → Backfill). |
| `monitors.py` | Add to `KNOWN_SHELTERS` (stale profiles, blank bios, empty/stale inventory). |
| `routes/api_routes.py` | New metro only: add `"City, ST": (lat, lon)` to `_REGION_COORDS` (IP location detection). |
| `public/js/preferences.js` | New metro only: add `'City, ST {emoji}'` to `regionCoords` (browser geolocation). Use the **exact** emoji stored in `location_display_name`. Then run `node build.js`. |
| `routes/recommender.py` | New metro only: add to `METRO_COORDS` ("nearby" suggestions). |

No changes are needed for browse/search/random-dog, SEO dog pages, `/{slug}` location routing, share URLs, or the recommender SQL view — they are data-driven from `shelters` / `active_dogs`.

---

## Phase 4: Database Setup

Insert the `shelters` row (idempotent upsert):

```python
from jobs.lib.db import get_supabase_client
get_supabase_client().table("shelters").upsert({
    "shelter_id": "{ACRONYM}",
    "shelter_name": "{Shelter Name}",
    "city": "{City}",
    "state": "{ST}",
    "location_name": "{City}, {ST}",
    "location_display_name": "{City}, {ST} {emoji}",
    "relative_path": "/{slug}",
    "website_url": "https://{official-site}/",
}, on_conflict="shelter_id").execute()
```

Also add the shelter to `SHELTER_WEBSITES` in `scripts/migrate_shelter_info.py` so the list stays the source of truth, then populate its adoption info right away (otherwise it fills at the next daily run, 09:30 UTC):

```bash
python -m jobs.shelter_process_details_job --force {ACRONYM}
```

**Emoji conventions (existing):** Tucson/Phoenix 🌵, NYC 🗽, LA/Jacksonville 🌴, Chicago 🫘, Texas 🤠, Philly 🔔, San Diego 🏖️, SF 🌉, Seattle 🌲, Dover 🐾, Denver 🏔️

> [!WARNING]
> The local `.env.local` points at the **production** Supabase project. Anything you run locally
> (scrapers, enrichment, inserts) is live immediately — and prod's scheduler will pick up new
> `active_dogs`/`animals` rows on its next `generate_prompts` run.
> The `shelters` row is what makes the location appear in the picker (`/api/locations`) and
> what puts dogs in the recommender view. Dogs with prompts are servable under "All locations"
> even without it.

**Soft launch (optional):** add the ID to `BETA_SHELTER_IDS` in `routes/api_routes.py` to hide the location from the picker for everyone except `BETA_ALLOWED_EMAILS` (env var). Since accounts are now guest/device-based, the allowed "email" is the device identity (`{uuid}@device.chattyhound.com`). This only hides the picker entry — dogs remain reachable via "All locations", browse and direct links.

---

## Phase 5: Backfill + Thresholds

1. Run the inventory job → populates `active_dogs`.
2. Run the profiles job until every dog has an `animals` row (Admin → Crons "Run now", or `python -m jobs.shelters.{x}.profiles` locally).
3. Check bio lengths: `SELECT animal_id, bio_length FROM animals WHERE shelter_id = '{ACRONYM}' ORDER BY 2;`
4. **All active dogs become chattable.** Dogs whose bio is shorter than the shelter threshold get the generic `generic_pup` persona and a "⚠️ Limited info" badge, and are served after richer matches. Pick the threshold so that dogs with genuinely thin bios fall below it (typical range 500–1500; MCACC is 6000 because evaluation notes inflate bios).
5. Enrichment: `generate_prompts` (every 30 min on Railway) picks new dogs up automatically, or use Admin → Backfill for the shelter to run facts → persona → prompt immediately.
6. Verify: `/api/random_dog?location={display name}`, Browse All with the location filter, chat with a rich and a limited dog, an agent recommendation for the metro, and ask a dog "how much is your adoption fee?" (should answer from `shelters.process_details` with an official link).

---

## Phase 6: Deploy

1. `node build.js` if anything under `public/` changed (commit the rebuilt `api/index.html`).
2. Commit + push to `main` → Railway auto-deploys. The new jobs start on their next cron fire.
3. After 24h, check `/admin/crons` for failures and `/admin/data` for the shelter's chattable count.

---

## File Checklist

- [ ] `jobs/shelters/{acronym_lower}/__init__.py`, `inventory.py`, `profiles.py`
- [ ] `jobs/shelter_registry.py` (inventory + profiles jobs)
- [ ] `jobs/lib/enrichment.py` (`_BIO_MIN_LENGTH`)
- [ ] `routes/admin_routes.py` (backfill job maps)
- [ ] `monitors.py` (`KNOWN_SHELTERS`)
- [ ] New metro: `routes/api_routes.py`, `public/js/preferences.js` (+ `node build.js`), `routes/recommender.py`
- [ ] `shelters` table row (incl. `website_url`) + `scripts/migrate_shelter_info.py`; run `shelter_process_details` for it
- [ ] Backfill inventory → profiles → enrichment; verify in UI
