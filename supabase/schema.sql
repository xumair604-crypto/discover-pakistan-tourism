-- =====================================================================
-- Discover Pakistan Tourism: database schema and security rules
-- Run this once in Supabase: Dashboard > SQL Editor > New query > Run.
-- Safe to run again; it only creates what is missing and refreshes rules.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Admins: only emails listed here can use admin.html.
-- Add each owner's email with:
--   insert into public.admins (email) values ('owner@example.com');
-- ---------------------------------------------------------------------
create table if not exists public.admins (
  email text primary key check (email = lower(email))
);
alter table public.admins enable row level security;
-- No policies on purpose: nobody can read or change this list from the
-- website. Manage it from the SQL Editor only.

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.admins
    where email = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;
revoke all on function public.is_admin() from public;
grant execute on function public.is_admin() to anon, authenticated;

create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------
-- Bookings and enquiries sent from the website
-- ---------------------------------------------------------------------
create table if not exists public.bookings (
  id               uuid primary key default gen_random_uuid(),
  ref              text not null unique check (ref ~ '^DP-[A-Z0-9]{4,10}$'),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  source           text not null default 'enquiry' check (source in ('enquiry', 'trip_builder')),
  name             text not null check (char_length(name) between 1 and 120),
  phone            text not null check (char_length(phone) between 3 and 40),
  email            text check (email is null or char_length(email) <= 200),
  service          text check (service is null or char_length(service) <= 80),
  destination      text check (destination is null or char_length(destination) <= 400),
  travel_date      date,
  guests           text check (guests is null or char_length(guests) <= 40),
  travelling_from  text check (travelling_from is null or char_length(travelling_from) <= 120),
  message          text check (message is null or char_length(message) <= 3000),
  details          jsonb not null default '{}'::jsonb check (pg_column_size(details) <= 8000),
  status           text not null default 'new'
                   check (status in ('new', 'contacted', 'quoted', 'confirmed', 'completed', 'cancelled')),
  quoted_rate      text check (quoted_rate is null or char_length(quoted_rate) <= 200),
  admin_notes      text check (admin_notes is null or char_length(admin_notes) <= 5000)
);
create index if not exists bookings_created_idx on public.bookings (created_at desc);
create index if not exists bookings_status_idx on public.bookings (status);

drop trigger if exists bookings_touch on public.bookings;
create trigger bookings_touch before update on public.bookings
  for each row execute function public.touch_updated_at();

alter table public.bookings enable row level security;

drop policy if exists "Website visitors can submit bookings" on public.bookings;
create policy "Website visitors can submit bookings" on public.bookings
  for insert to anon, authenticated
  with check (status = 'new' and quoted_rate is null and admin_notes is null);

drop policy if exists "Admins can read bookings" on public.bookings;
create policy "Admins can read bookings" on public.bookings
  for select to authenticated using (public.is_admin());

drop policy if exists "Admins can update bookings" on public.bookings;
create policy "Admins can update bookings" on public.bookings
  for update to authenticated using (public.is_admin()) with check (public.is_admin());

drop policy if exists "Admins can delete bookings" on public.bookings;
create policy "Admins can delete bookings" on public.bookings
  for delete to authenticated using (public.is_admin());

-- ---------------------------------------------------------------------
-- Website content
-- ---------------------------------------------------------------------
create table if not exists public.tours (
  id          text primary key check (id ~ '^[a-z0-9-]{2,40}$'),
  sort        integer not null default 100,
  published   boolean not null default true,
  region      text not null,
  length      text not null default 'short' check (length in ('day', 'short', 'long')),
  days        text not null default '',
  title       text not null,
  summary     text not null default '',
  season      text not null default '',
  start_from  text not null default '',
  img         text not null default '',
  alt         text not null default '',
  plan        jsonb not null default '[]'::jsonb,
  incl        jsonb not null default '[]'::jsonb,
  excl        jsonb not null default '[]'::jsonb,
  note        text,
  updated_at  timestamptz not null default now()
);

create table if not exists public.offers (
  id          uuid primary key default gen_random_uuid(),
  sort        integer not null default 100,
  published   boolean not null default true,
  title       text not null,
  body        text not null default '',
  updated_at  timestamptz not null default now()
);

create table if not exists public.hotels (
  id          uuid primary key default gen_random_uuid(),
  sort        integer not null default 100,
  published   boolean not null default true,
  name        text not null,
  details     text not null default '',
  icon        text not null default 'buildings' check (icon ~ '^[a-z-]{2,40}$'),
  updated_at  timestamptz not null default now()
);

create table if not exists public.venues (
  id          uuid primary key default gen_random_uuid(),
  sort        integer not null default 100,
  published   boolean not null default true,
  name        text not null,
  details     text not null default '',
  updated_at  timestamptz not null default now()
);

do $$
declare t text;
begin
  foreach t in array array['tours', 'offers', 'hotels', 'venues'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop trigger if exists %I on public.%I', t || '_touch', t);
    execute format('create trigger %I before update on public.%I for each row execute function public.touch_updated_at()', t || '_touch', t);
    execute format('drop policy if exists "Anyone can read published content" on public.%I', t);
    execute format('create policy "Anyone can read published content" on public.%I for select to anon, authenticated using (published or public.is_admin())', t);
    execute format('drop policy if exists "Admins manage content" on public.%I', t);
    execute format('create policy "Admins manage content" on public.%I for all to authenticated using (public.is_admin()) with check (public.is_admin())', t);
  end loop;
end $$;

-- Table privileges (row level security above decides which rows).
grant usage on schema public to anon, authenticated;
grant insert on public.bookings to anon, authenticated;
grant select, update, delete on public.bookings to authenticated;
grant select on public.tours, public.offers, public.hotels, public.venues to anon, authenticated;
grant insert, update, delete on public.tours, public.offers, public.hotels, public.venues to authenticated;
revoke all on public.admins from anon, authenticated;
