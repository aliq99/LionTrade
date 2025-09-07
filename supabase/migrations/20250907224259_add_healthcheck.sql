create table if not exists public.healthcheck (
  id bigserial primary key,
  created_at timestamptz default now()
);
