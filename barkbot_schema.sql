create table if not exists scrape_runs (
  id bigint generated always as identity primary key,
  triggered_by text not null,
  source_count integer not null default 0,
  processed_count integer not null default 0,
  inserted_count integer not null default 0,
  updated_count integer not null default 0,
  unchanged_count integer not null default 0,
  error_count integer not null default 0,
  status text not null default 'running',
  notes text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table if not exists animals (
  animal_id text primary key,
  url text not null,
  located_at text,
  description text,
  weight text,
  age text,
  more_info text,
  bio text,
  data_updated text,
  image_url text,
  image_file text,
  image_public_url text,
  record_hash text not null,
  qa_status text not null default 'pending',
  qa_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_scrape_run_id bigint references scrape_runs(id)
);

create index if not exists idx_animals_updated_at on animals(updated_at desc);
create index if not exists idx_animals_qa_status on animals(qa_status);

create table if not exists animal_versions (
  id bigint generated always as identity primary key,
  animal_id text not null references animals(animal_id) on delete cascade,
  version_no integer not null,
  captured_at timestamptz not null default now(),
  snapshot jsonb not null,
  record_hash text not null,
  scrape_run_id bigint references scrape_runs(id),
  unique(animal_id, version_no)
);

create index if not exists idx_animal_versions_animal_id on animal_versions(animal_id, version_no desc);

create table if not exists animal_change_events (
  id bigint generated always as identity primary key,
  animal_id text not null references animals(animal_id) on delete cascade,
  change_type text not null check (change_type in ('inserted', 'updated', 'unchanged', 'removed')),
  changed_fields text[] not null default '{}',
  diff jsonb not null default '{}'::jsonb,
  scrape_run_id bigint references scrape_runs(id),
  created_at timestamptz not null default now()
);

create index if not exists idx_animal_change_events_animal_id on animal_change_events(animal_id, created_at desc);
create index if not exists idx_animal_change_events_created_at on animal_change_events(created_at desc);

create table if not exists pima_all_dogs (
  animal_id text primary key,
  name text,
  gender text,
  age text,
  weight text,
  location text,
  view_type text,
  image_url text,
  scraped_at timestamptz default now()
);
