import os, json, urllib.request, collections
U = os.environ["SUPABASE_URL"].rstrip("/"); K = os.environ["SUPABASE_KEY"]

def get(t, q):
    r = urllib.request.Request(f"{U}/rest/v1/{t}?{q}",
        headers={"apikey": K, "Authorization": "Bearer " + K})
    return json.load(urllib.request.urlopen(r, timeout=120))

ev = get("ga4_event_daily", "select=day,event_name,event_count,total_users&limit=100000")
alld = sorted({r["day"] for r in ev})
print(f"CUA SO: {alld[0]} -> {alld[-1]}  ({len(alld)} ngay co du lieu)\n")

W = ["GA4_click_form_submit","form_start","form_submit","GA4_Form_Submit",
     "GA4_click_hotline","GA4_click_messenger","GA4_click_zalo","generate_lead","k20_contact_click"]
m = collections.defaultdict(lambda: collections.defaultdict(int))
for r in ev:
    if r["event_name"] in W:
        m[r["event_name"]][r["day"][:7]] += r["event_count"] or 0
months = sorted({d for k in m for d in m[k]})
print("=== SU KIEN THEO THANG ===")
print("event".ljust(24) + "".join(x.rjust(10) for x in months))
for k in W:
    if k in m:
        print(k.ljust(24) + "".join(f"{m[k].get(x,0):,}".rjust(10) for x in months))

print("\n=== NGAY NAO CO, NGAY NAO KHONG ===")
for k in ["GA4_click_zalo","GA4_click_hotline","GA4_click_messenger","generate_lead","GA4_Form_Submit","form_submit"]:
    ds = sorted([(r["day"], r["event_count"] or 0) for r in ev if r["event_name"] == k])
    nz = [d for d, c in ds if c > 0]
    print(f"{k:<24} co mat {len(nz):>3}/{len(alld)} ngay | dau {nz[0] if nz else '-'} | cuoi {nz[-1] if nz else '-'} | tong {sum(c for _,c in ds):,}")
    if k == "GA4_click_zalo":
        print("      chi tiet zalo:", ", ".join(f"{d}={c}" for d, c in ds if c > 0))

fs = sorted([(r["day"], r["event_count"] or 0) for r in ev if r["event_name"] == "form_submit"])
if fs:
    print(f"\nform_submit: {len(fs)} ngay | tb {sum(c for _,c in fs)/len(fs):.1f}/ngay | cao nhat {max(c for _,c in fs)}")
    print("  10 ngay cao nhat:", ", ".join(f"{d}={c}" for d, c in sorted(fs, key=lambda x: -x[1])[:10]))

print("\n=== TRANG DICH: phien | key_events ===")
lp = get("ga4_landing_daily", "select=landing_page,sessions,key_events&limit=100000")
agg = collections.defaultdict(lambda: [0, 0.0])
for r in lp:
    a = agg[r["landing_page"]]; a[0] += r["sessions"] or 0; a[1] += float(r["key_events"] or 0)
for p, (s, k) in sorted(agg.items(), key=lambda kv: -kv[1][0])[:15]:
    print(f"  {s:>7,} {k:>8.0f}  {p[:76]}")
print(f"  TONG key_events tren moi trang dich: {sum(v[1] for v in agg.values()):,.0f}")

print("\n=== META THEO CHIEN DICH ===")
mc = get("meta_campaign_daily", "select=campaign_name,objective,spend,impressions,reach,clicks,link_clicks,results,result_type&limit=100000")
c = collections.defaultdict(lambda: collections.defaultdict(float))
rt = {}
for r in mc:
    k = (r["campaign_name"] or "?")
    rt[k] = r["result_type"] or rt.get(k, "")
    for f in ["spend","impressions","reach","clicks","link_clicks","results"]:
        c[k][f] += float(r[f] or 0)
    c[k]["obj"] = 0
objs = {(r["campaign_name"] or "?"): (r["objective"] or "") for r in mc}
for k, v in sorted(c.items(), key=lambda kv: -kv[1]["spend"]):
    f = v["impressions"] / v["reach"] if v["reach"] else 0
    cpm = v["spend"] / v["impressions"] * 1000 if v["impressions"] else 0
    print(f"  {k[:44]:<44} {objs.get(k,''):<22} chi={v['spend']:>13,.0f} tansuat={f:>5.2f} CPM={cpm:>9,.0f} nhap={v['clicks']:>7,.0f} lknhap={v['link_clicks']:>7,.0f} ketqua={v['results']:>6,.0f} {rt.get(k,'')}")
