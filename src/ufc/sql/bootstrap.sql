create schema if not exists raw;
create schema if not exists src;

-- Every distinct version of every upstream file. Content is never changed; last_seen_at is bumped
-- whenever the same version is fetched again, so a revert upstream makes the old version current again.
create table if not exists raw.file_snapshots (
    snapshot_id   bigserial unique,
    file_name     text        not null,
    sha256        text        not null,
    source_commit text,
    fetched_at    timestamptz not null,
    row_count     int         not null,
    content       bytea       not null,
    last_seen_at  timestamptz not null,
    primary key (file_name, sha256)
);
alter table raw.file_snapshots add column if not exists last_seen_at timestamptz;

-- One row per load of a file into src.<file>.
create table if not exists src.load_log (
    id                 bigserial primary key,
    file_name          text        not null,
    sha256             text        not null,
    loaded_at          timestamptz not null default now(),
    row_count          int         not null,
    previous_row_count int
);

-- Which fighter is "<name>" in this fight, and how we decided.
create table if not exists src.fighter_identity (
    fight_id        text not null,
    name_as_written text not null,
    fighter_id      text,
    method          text not null,
    primary key (fight_id, name_as_written)
);
