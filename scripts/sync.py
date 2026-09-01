#!/usr/bin/env python3
"""nguoilonbinhan.meschool - keo GA4 + Search Console + Meta Ads -> Supabase.
Chay tren GitHub Actions. Khoa lay tu bien moi truong, khong luu trong repo.
  GA_SA_KEY      : noi dung file JSON cua service account
  SUPABASE_URL   : https://xxx.supabase.co
  SUPABASE_KEY   : service_role key
  META_TOKEN     : system user token cua Meta (quyen ads_read)
"""
import json, os, sys, urllib.request, urllib.error, urllib.parse, datetime
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


def google_post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


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
        with urllib.request.urlopen(req, timeout=180) as r:
            r.read()
    print(f"  {table:20s} {len(rows)} dong")
    return len(rows)


total = 0

# ---------- GA4 ----------
r = google_post(
    f"https://analyticsdata.googleapis.com/v1beta/properties/{GA4_PROPERTY}:runReport", {
    "dateRanges": [{"startDate": str(start), "endDate": str(end)}],
    "dimensions": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}],
    "metrics": [{"name": "sessions"}, {"name": "activeUsers"},
                {"name": "newUsers"}, {"name": "screenPageViews"}],
    "limit": 100000})
rows = []
for row in r.get("rows", []):
    d = row["dimensionValues"][0]["value"]
    m = [int(x["value"]) for x in row["metricValues"]]
    rows.append({"day": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                 "channel": row["dimensionValues"][1]["value"],
                 "sessions": m[0], "active_users": m[1],
                 "new_users": m[2], "pageviews": m[3]})
total += upsert("ga4_daily_channel", rows)

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
     "position": round(x["position"], 2)} for x in gsc("query", 500)])

total += upsert("gsc_page", [
    {"snapshot_on": TODAY, "page": x["keys"][0], "clicks": x["clicks"],
     "impressions": x["impressions"], "ctr": round(x["ctr"], 5),
     "position": round(x["position"], 2)} for x in gsc("page", 500)])

# ---------- Meta Ads ----------
def graph_get(path, params):
    params = dict(params, access_token=META_TOKEN)
    url = f"https://graph.facebook.com/{GRAPH_VER}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        print(f"  Meta loi {e.code} tai {path}: {body}")
        raise


def num(v, typ=int):
    try:
        return typ(float(v))
    except (TypeError, ValueError):
        return None


if META_TOKEN:
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
            rows.append({"day": x["date_start"],
                         "account_id": acc["id"],
                         "account_name": acc.get("name"),
                         "spend": num(x.get("spend"), float),
                         "impressions": num(x.get("impressions")),
                         "reach": num(x.get("reach")),
                         "clicks": num(x.get("clicks"))})
    total += upsert("meta_ad_daily", rows)
else:
    print("Bo qua Meta: chua co META_TOKEN")

# ---------- nhat ky ----------
upsert("ingest_run", [{"source": "github_actions", "window_start": str(start),
                       "window_end": str(end), "rows_written": total,
                       "status": "ok", "message": "sync.py tren GitHub Actions"}])
print(f"Xong. Tong {total} dong.")
