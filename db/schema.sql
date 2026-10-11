-- VC Pulse schema. Plain Postgres: runs the same on Neon or Supabase.

-- Vikram's pipeline: one row per investor.
create table if not exists vcs (
  id                 serial primary key,
  -- Vikram's columns (only the founder role may change these)
  name               text not null,
  firm               text not null,
  thesis             text,
  region             text,
  status             text not null default 'yet_to_reach_out'
                       check (status in ('yet_to_reach_out', 'waiting_response')),
  last_contact_date  date,
  contact_history    text,
  notes              text,
  feed_url           text,
  -- Signal-derived columns (only the engine role may change these)
  last_signal_date   date,
  signal_summary     text,
  follow_up_score    int check (follow_up_score between 0 and 100),
  recommended_action text,
  unique (name, firm)
);

-- Every piece of evidence the engine found, with its source link.
create table if not exists signals (
  id         bigserial primary key,
  vc_id      int not null references vcs(id) on delete cascade,
  url        text not null,
  title      text not null,
  source     text,
  origin     text not null,            -- news | firm_news | blog | podcast | search
  published  date not null,
  kind       text,                     -- invested | wrote | said | appeared | mentioned
  relevance  int,                      -- 0..3 fit with B2B logistics / supply chain
  about_vc   boolean,                  -- is this VC (or their firm) actually the actor?
  summary    text,
  points     numeric,
  run_id     int,
  first_seen timestamptz not null default now(),
  unique (vc_id, url)
);
create index if not exists signals_vc_published on signals (vc_id, published desc);

-- One row per engine run (twice a week by cron, or "Run now").
create table if not exists runs (
  id               serial primary key,
  trigger          text not null,       -- cron | manual
  started_at       timestamptz not null default now(),
  finished_at      timestamptz,
  status           text not null default 'running',
  vcs_total        int default 0,
  vcs_done         int default 0,
  items_scanned    int default 0,
  signals_kept     int default 0,
  hot_count        int default 0,
  quiet_count      int default 0,
  errors           int default 0,
  notes_hash_before text,               -- fingerprint of Vikram's columns before the run
  notes_hash_after  text,               -- ...and after. Equal = nothing of his was touched.
  sources          jsonb,
  log              jsonb default '[]'::jsonb
);

-- Before/after snapshot of each VC's signal columns per run (powers "what changed").
create table if not exists vc_changes (
  run_id     int not null references runs(id) on delete cascade,
  vc_id      int not null references vcs(id) on delete cascade,
  old_score  int,
  new_score  int,
  old_action text,
  new_action text,
  primary key (run_id, vc_id)
);
