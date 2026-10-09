-- tenants & users
create extension if not exists pgcrypto;

create table if not exists tenants (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  plan text default 'free',
  created_at timestamptz not null default now()
);

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  email text not null,
  name text,
  role text not null default 'admin',
  created_at timestamptz not null default now()
);

-- agents
create table if not exists agents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null,
  system_prompt text,
  model text default 'phi3',
  active boolean default true,
  created_at timestamptz not null default now()
);

-- oauth connections (per channel/provider)
create table if not exists connections (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  provider text not null,
  account_label text,
  oauth_data_json jsonb not null default '{}'::jsonb,
  scopes text[] not null default '{}',
  expires_at timestamptz,
  created_at timestamptz not null default now()
);

-- jobs & messages & artifacts
create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  agent_id uuid references agents(id) on delete set null,
  status text not null default 'queued', -- queued|running|succeeded|failed
  payload_json jsonb not null default '{}'::jsonb,
  result_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  job_id uuid references jobs(id) on delete cascade,
  role text not null, -- system|user|assistant
  content text not null,
  meta_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists artifacts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  job_id uuid references jobs(id) on delete cascade,
  kind text not null, -- image|poster|file|link
  url text not null,
  meta_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
