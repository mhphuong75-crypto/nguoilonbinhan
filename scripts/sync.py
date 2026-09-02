#!/usr/bin/env python3
"""nguoilonbinhan.meschool - keo GA4 + Search Console + Meta Ads -> Supabase.
Chay tren GitHub Actions. Khoa lay tu bien moi truong, khong luu trong repo.
  GA_SA_KEY      : noi dung file JSON cua service account
  SUPABASE_URL   : https://xxx.supabase.co
  SUPABASE_KEY   : service_role key
  META_TOKEN     : system user token cua Meta (quyen ads_read)

v3 - them:
  ga4_event_daily    : moi su kien GA4 dang ghi nhan (de biet web co form hay khong)
  ga4_landing_daily  : traffic theo trang dich + muc do doc
  Meta khong con lam sap ca lan chay khi loi
"""
import json, os, sys, urllib.request, urllib.error, urllib.parse, datetime, traceback

from google.oauth2 import service_account
import google.auth.transport.requests

GA4_PROPERTY = "413850223"
SITE_URL     = "https://meschool.vn/"
GRAPH_VER    = "v23.0"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 90

SB_URL = os.environ["SUPABASE_URL"].rstrip("/")
SB_KEY = os.environ["SUPABASE_KEY"]
META_TOKEN = os.environ.get("META_TOKEN", "").strip()

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly",
          "https://www.googleapis.com/auth/webmasters.readonly"]
creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ["GA_SA_KEY"]), scopes=SCOPES)
creds.refresh(google.auth.transport.requests.Request())
TOKEN = creds.token

end   = datetime.date.today() - datetime.timedelta(days=1)
start = end - datetime.timedelta(days=DAYS - 1)
TODAY = str(datetime.date.today())
print(f"Cua so du lieu: {start} -> {end}")

GA4_URL = f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport"


def google_post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def ga4(dimensions, metrics, limit=100000, order=None):
    """Tra ve list[dict] voi key = ten dimension/metric."""
    body = {"dateRanges": [{"startDate": str(start), "endDate": str(end)}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics":    [{"name": m} for m in metrics],
            "limit": limit}
    if order:
        body["orderBys"] = [{"metric": {"metricName": order}, "desc": True}]
    r = google_post(GA4_URL, body)
    out = []
    for row in r.get("rows", []):
        rec = {}
        for i, d in enumerate(dimensions):
            rec[d] = row["dimensionValues"][i]["value"]
        for i, m in enumerate(metrics):
            rec[m] = row["metricValues"][i]["value"]
        out.append(rec)
    return out


def ymd(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def num(v, typ=int, nd=None):
    try:
        x = typ(float(v))
        return round(x, nd) if nd is not None else x
    except (TypeError, ValueError):
        return None


def upsert(table, rows, chunk=400):
    if not rows:
        print(f"  {table:20s} 0 dong"); return 0
    for i in range(0, len(rows), chunk):
        req = urllib.request.Request(
            f"{SB_URL}/rest/v1/{table}",
            data=json.dumps(rows[i:i+chunk]).encode("utf-8"), method="POST",
            headers={"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY,
                     "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                r.read()
        except urllib.error.HTTPError as e:
            print(f"  {table}: loi {e.code} -> {e.read().decode('utf-8','replace')[:400]}")
            raise
    print(f"  {table:20s} {len(rows)} dong")
    return len(rows)


total = 0
notes = []

# ---------- GA4: kenh theo ngay (nhu cu) ----------
total += upsert("ga4_daily_channel", [
    {"day": ymd(x["date"]), "channel": x["sessionDefaultChannelGroup"],
     "sessions": num(x["sessions"]), "active_users": num(x["activeUsers"]),
     "new_users": num(x["newUsers"]), "pageviews": num(x["screenPageViews"])}
    for x in ga4(["date", "sessionDefaultChannelGroup"],
                 ["sessions", "activeUsers", "newUsers", "screenPageViews"])])

# ---------- GA4: SU KIEN  (viec 2 - website co cho giơ tay khong?) ----------
try:
    ev = ga4(["date", "eventName"], ["eventCount", "totalUsers"])
    total += upsert("ga4_event_daily", [
        {"day": ymd(x["date"]), "event_name": x["eventName"],
         "event_count": num(x["eventCount"]), "total_users": num(x["totalUsers"])}
        for x in ev])

    agg = {}
    for x in ev:
        agg[x["eventName"]] = agg.get(x["eventName"], 0) + int(float(x["eventCount"]))
    print("\n=== DANH SACH SU KIEN GA4 DANG GHI NHAN ===")
    for name, c in sorted(agg.items(), key=lambda kv: -kv[1]):
        print(f"    {name:40s} {c:>10,}")
    print("=== HET DANH SACH ===\n")
    notes.append(f"ga4_events={len(agg)}")
except Exception:
    print("  ga4_event_daily: LOI"); traceback.print_exc()
    notes.append("ga4_events=LOI")

# ---------- GA4: TRANG DICH (viec 3 - noi traffic voi noi dung) ----------
LAND_FULL = ["sessions", "engagedSessions", "engagementRate",
             "averageSessionDuration", "keyEvents"]
LAND_MIN  = ["sessions", "engagedSessions", "engagementRate",
             "averageSessionDuration"]
try:
    try:
        lp = ga4(["date", "landingPage"], LAND_FULL, limit=50000, order="sessions")
        has_ke = True
    except urllib.error.HTTPError:
        print("  keyEvents khong dung duoc, thu lai khong co no")
        lp = ga4(["date", "landingPage"], LAND_MIN, limit=50000, order="sessions")
        has_ke = False
    total += upsert("ga4_landing_daily", [
        {"day": ymd(x["date"]), "landing_page": x["landingPage"][:500],
         "sessions": num(x["sessions"]),
         "engaged_sessions": num(x["engagedSessions"]),
         "engagement_rate": num(x["engagementRate"], float, 4),
         "avg_engagement_sec": num(x["averageSessionDuration"], float, 1),
         "key_events": num(x["keyEvents"], float, 2) if has_ke else None}
        for x in lp])
except Exception:
    print("  ga4_landing_daily: LOI"); traceback.print_exc()
    notes.append("ga4_landing=LOI")

# ---------- Search Console ----------
sc = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
      + urllib.parse.quote(SITE_URL, safe="") + "/searchAnalytics/query")


def gsc(dimension, limit):
    d = google_post(sc, {"startDate": str(start), "endDate": str(end),
                         "dimensions": [dimension], "rowLimit": limit})
    return d.get("rows", [])


total += upsert("gsc_daily", [
    {"day": x["keys"][0], "clicks": x["clicks"], "impressions": x["impressions"],
     "ctr": round(x["ctr"], 5), "position": round(x["position"], 2)}
    for x in gsc("date", 1000)])

total += upsert("gsc_query", [
    {"snapshot_on": TODAY, "query": x["keys"][0], "clicks": x["clicks"],
     "impressions": x["impressions"], "ctr": round(x["ctr"], 5),
     "position": round(x["position"], 2)} for x in gsc("query", 1000)])

total += upsert("gsc_page", [
    {"snapshot_on": TODAY, "page": x["keys"][0], "clicks": x["clicks"],
     "impressions": x["impressions"], "ctr": round(x["ctr"], 5),
     "position": round(x["position"], 2)} for x in gsc("page", 1000)])


# ---------- Meta Ads ----------
def graph_get(path, params):
    params = dict(params, access_token=META_TOKEN)
    url = f"https://graph.facebook.com/{GRAPH_VER}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        print(f"  Meta loi {e.code} tai {path}: {body}")
        raise


if META_TOKEN:
    try:
        accounts = graph_get("me/adaccounts", {"fields": "id,name", "limit": 100}).get("data", [])
        print(f"Meta: thay {len(accounts)} tai khoan quang cao")
        rows = []
        for acc in accounts:
            d = graph_get(f"{acc['id']}/insights", {
                "level": "account", "time_increment": 1,
                "fields": "spend,impressions,reach,clicks",
                "time_range": json.dumps({"since": str(start), "until": str(end)}),
                "limit": 500})
            got = d.get("data", [])
            print(f"    {acc.get('name','?'):28s} {len(got)} ngay")
            for x in got:
                rows.append({"day": x["date_start"], "account_id": acc["id"],
                             "account_name": acc.get("name"),
                             "spend": num(x.get("spend"), float, 2),
                             "impressions": num(x.get("impressions")),
                             "reach": num(x.get("reach")),
                             "clicks": num(x.get("clicks"))})
        total += upsert("meta_ad_daily", rows)

        # ----- campaign-level: tien di dau, campaign nao dot -----
        RESULT_PRIORITY = [
            ("onsite_conversion.messaging_conversation_started_7d", "tin nhan"),
            ("onsite_conversion.lead_grouped", "lead"),
            ("lead", "lead"),
            ("offsite_conversion.fb_pixel_lead", "lead"),
            ("offsite_conversion.fb_pixel_complete_registration", "dang ky"),
            ("landing_page_view", "xem trang dich"),
            ("link_click", "nhap lien ket"),
            ("post_engagement", "tuong tac bai"),
        ]

        def pick_result(actions):
            m = {a.get("action_type"): a.get("value") for a in (actions or [])}
            for key, label in RESULT_PRIORITY:
                if key in m:
                    return num(m[key]), label
            return None, None

        crows = []
        for acc in accounts:
            params = {
                "level": "campaign", "time_increment": 1,
                "fields": ("campaign_id,campaign_name,objective,spend,impressions,reach,"
                           "clicks,inline_link_clicks,actions"),
                "time_range": json.dumps({"since": str(start), "until": str(end)}),
                "limit": 500}
            path, page = f"{acc['id']}/insights", 0
            while path and page < 40:
                d = graph_get(path, params) if page == 0 else json.load(
                    urllib.request.urlopen(path, timeout=180))
                for x in d.get("data", []):
                    res, rtype = pick_result(x.get("actions"))
                    crows.append({
                        "day": x["date_start"], "account_id": acc["id"],
                        "account_name": acc.get("name"),
                        "campaign_id": x.get("campaign_id") or "?",
                        "campaign_name": x.get("campaign_name"),
                        "objective": x.get("objective"),
                        "spend": num(x.get("spend"), float, 2),
                        "impressions": num(x.get("impressions")),
                        "reach": num(x.get("reach")),
                        "clicks": num(x.get("clicks")),
                        "link_clicks": num(x.get("inline_link_clicks")),
                        "results": res, "result_type": rtype})
                path = (d.get("paging") or {}).get("next")
                page += 1
            print(f"    campaign {acc.get('name','?'):22s} tong {len(crows)} dong")
        total += upsert("meta_campaign_daily", crows)
    except Exception:
        # Meta hong thi chi mot minh no hong, khong keo do phan Google
        print("  meta_ad_daily: LOI - bo qua, phan Google van giu nguyen")
        traceback.print_exc()
        notes.append("meta=LOI")
else:
    print("Bo qua Meta: chua co META_TOKEN")

# ---------- nhat ky ----------
upsert("ingest_run", [{"source": "github_actions", "window_start": str(start),
                       "window_end": str(end), "rows_written": total,
                       "status": "partial" if any("LOI" in x for x in notes) else "ok",
                       "message": "sync.py v3 " + (";".join(notes) if notes else "day du")}])
print(f"Xong. Tong {total} dong. {notes}")
