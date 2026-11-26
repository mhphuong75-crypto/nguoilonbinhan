-- Approved by Hien on 26/11/2026 and applied to Supabase. Campus/day aggregate counts only; no student/parent identifiers.
create table public.nlba_tuyen_sinh_daily_snapshot (
 snapshot_ts timestamptz primary key,
 source text not null,
 deposit_rows integer not null check(deposit_rows>=0),
 expected_rows integer not null check(expected_rows>=0),
 union_rows integer not null check(union_rows>=0),
 data jsonb not null check(jsonb_typeof(data)='array')
);
alter table public.nlba_tuyen_sinh_daily_snapshot enable row level security;
revoke all on public.nlba_tuyen_sinh_daily_snapshot from anon,authenticated;
grant select on public.nlba_tuyen_sinh_daily_snapshot to authenticated;
create policy nlba_company_read_admissions_aggregate
 on public.nlba_tuyen_sinh_daily_snapshot for select to authenticated
 using (lower(coalesce((select auth.jwt()->>'email'),'')) like '%@meschool.vn'
 or lower(coalesce((select auth.jwt()->>'email'),''))='mhphuong75@gmail.com');
comment on table public.nlba_tuyen_sinh_daily_snapshot is
 'Campus/day counts only. No names, phone numbers, or CRM record identifiers. Registrations by deposit date; planned schedules exclude closed CRM stages.';
