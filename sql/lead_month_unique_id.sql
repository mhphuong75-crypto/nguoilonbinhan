create table public.nlba_crm_lead_month_snapshot (
 lead_id text primary key, ngay_tao date not null, campus text, nguon text, captured_at timestamptz not null
);
alter table public.nlba_crm_lead_month_snapshot enable row level security;
revoke all on public.nlba_crm_lead_month_snapshot from public, anon;
grant select on public.nlba_crm_lead_month_snapshot to authenticated;
grant all on public.nlba_crm_lead_month_snapshot to service_role;
create policy nlba_lead_month_read on public.nlba_crm_lead_month_snapshot for select to authenticated using (
 (auth.jwt()->>'email') ilike '%@meschool.vn' or (auth.jwt()->>'email')='mhphuong75@gmail.com'
);
create view public.v_nlba_crm_lead_month with (security_invoker=true) as
with raw_latest as (
 select distinct on (du_lieu->>'ID') du_lieu d,ts
 from public.stg_raw where nguon='amis_opportunity' and nullif(du_lieu->>'ID','') is not null
 order by du_lieu->>'ID',ts desc,id desc
), raw_rows as (
 select d->>'ID' lead_id, substring(d->>'CreatedDate',1,7) thang,
 coalesce(nullif(nullif(btrim(d->>'CustomField17Text'),''),'-'),s.campus,'(chưa gán)') campus,
 coalesce(nullif(nullif(btrim(d->>'LeadSourceIDText'),''),'-'),'(chưa gắn)') nguon,ts
 from raw_latest r left join public.nlba_crm_lead_month_snapshot s on s.lead_id=r.d->>'ID'
 where d->>'CreatedDate' ~ '^\d{4}-\d{2}-\d{2}'
), snap as (
 select lead_id,to_char(ngay_tao,'YYYY-MM') thang,coalesce(campus,'(chưa gán)') campus,coalesce(nguon,'(chưa gắn)') nguon,captured_at ts from public.nlba_crm_lead_month_snapshot
), raw_stamp as(select thang,max(ts) ts from raw_rows group by thang),
 snap_stamp as(select thang,max(ts) ts from snap group by thang),
 chosen as(
 select r.* from raw_rows r left join snap_stamp s using(thang) join raw_stamp a using(thang) where s.ts is null or a.ts>s.ts
 union all
 select s.* from snap s join snap_stamp a using(thang) left join raw_stamp r using(thang) where (r.ts is null or a.ts>=r.ts) and s.ts=a.ts
)
select thang,campus,nguon,count(*)::integer so_lead,max(ts) snapshot_ts from chosen group by thang,campus,nguon;
revoke all on public.v_nlba_crm_lead_month from public, anon;
grant select on public.v_nlba_crm_lead_month to authenticated,service_role;
