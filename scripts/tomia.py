#!/usr/bin/env python3
"""nguoilonbinhan.meschool - boc file Tomia trong kho 'kho-tho'.

Moi tep Tomia co 6 sheet:
  01. TONG QUAN THEO TRUONG   -> tomia_ngay        (tong hop moi truong moi ngay)
  02. Diem danh - Chi tiet    -> tomia_diem_danh   (1 tre x 1 ngay)
  03. Dan thuoc - Chi tiet    -> tomia_dan_thuoc
  04. Gop y - Chi tiet        -> tomia_gop_y
  05. Van hanh - Chi tiet     -> tomia_ticket      (su co)
  06. Van hanh - Tre          -> tomia_ticket_tre
"""
import io, os, re, json, hashlib, datetime, urllib.request

import openpyxl

SB_URL = os.environ["SUPABASE_URL"].rstrip("/")
SB_KEY = os.environ["SUPABASE_KEY"]
BUCKET = "kho-tho"
PREFIX = "tomia/"

SHEET_TONG = "01. TỔNG QUAN THEO TRƯỜNG"
CHI_SO = ["di_hoc", "vang", "den_muon", "ve_muon",
          "tre_dan_thuoc", "cu_thuoc", "da_uong",
          "gy_moi", "gy_dang_xl", "gy_hoan_tat", "gy_mo_lai",
          "vh_dang_xl", "vh_da_dong", "vh_cao", "vh_tb", "vh_thap"]


def goi(url, method="GET", body=None, headers=None, raw=False):
    h = {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY}
    h.update(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read() if raw else r.read().decode()


def ghi(bang, dong, xung_dot):
    for i in range(0, len(dong), 1000):
        goi(f"{SB_URL}/rest/v1/{bang}?on_conflict={xung_dot}", "POST", dong[i:i + 1000],
            {"Prefer": "resolution=merge-duplicates,return=minimal"})


def danh_sach_tep():
    out = goi(f"{SB_URL}/storage/v1/object/list/{BUCKET}", "POST",
              {"prefix": PREFIX, "limit": 200,
               "sortBy": {"column": "created_at", "order": "asc"}})
    return [PREFIX + o["name"] for o in json.loads(out) if o.get("name", "").endswith(".xlsx")]


def nam_tu_ten(ten):
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", ten)
    return (int(m.group(3)), int(m.group(2))) if m else (datetime.date.today().year, 1)


def so(v):
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def chu(v, n=400):
    if v is None:
        return None
    s = str(v).strip()
    return s[:n] or None


def ngay_tu(v):
    """Nhan datetime, '2026-05-04', '24/01/2026 16:35', '17:20 06/05/2026'."""
    if v is None or v == "":
        return None
    if isinstance(v, (datetime.datetime, datetime.date)):
        return str(v.date() if isinstance(v, datetime.datetime) else v)
    s = str(v).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return str(datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            return None
    return None


def gio_tu(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M")
    m = re.search(r"(\d{1,2}):(\d{2})", str(v))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def tim_tieu_de(rows, moc, toi_da=12):
    """Tim dong tieu de chua tu khoa 'moc'; tra ve (chi_so_dong, danh sach ten cot)."""
    for i, r in enumerate(rows[:toi_da]):
        v = [chu(c, 80) or "" for c in r]
        if any(moc.lower() in x.lower() for x in v):
            return i, v
    return None, None


def cot_map(tieu_de):
    return {t.strip().lower(): i for i, t in enumerate(tieu_de) if t and t.strip()}


def lay(r, m, *khoa):
    for k in khoa:
        i = m.get(k)
        if i is not None and i < len(r):
            return r[i]
    return None


# ---------- sheet 01 ----------
def boc_tong_quan(ws, ten_tep):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if len(rows) < 6:
        return []
    nam, thang_dau = nam_tu_ten(ten_tep)
    cot_ngay = []
    for c, v in enumerate(rows[2]):
        if isinstance(v, str) and v.strip().startswith("Ngày"):
            m = re.search(r"(\d{2})/(\d{2})", v)
            if not m:
                continue
            d_, t_ = int(m.group(1)), int(m.group(2))
            n = nam + 1 if t_ < thang_dau else nam
            try:
                cot_ngay.append((c, datetime.date(n, t_, d_)))
            except ValueError:
                pass
    out = []
    for r in rows[5:]:
        ma = chu(r[0], 40)
        if not ma or ma.upper().startswith("TỔNG"):
            continue
        ten = chu(r[1], 120) if len(r) > 1 else None
        for c, d in cot_ngay:
            khoi = r[c:c + 16]
            gt = {k: so(khoi[i]) if i < len(khoi) else None for i, k in enumerate(CHI_SO)}
            if all(v is None for v in gt.values()):
                continue
            gt.update({"ngay": str(d), "ma_truong": ma, "ten_truong": ten, "tep": ten_tep})
            out.append(gt)
    return out


# ---------- sheet 02 ----------
def boc_diem_danh(ws):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    i, td = tim_tieu_de(rows, "Mã trẻ")
    if i is None:
        return []
    m = cot_map(td)
    out, thay = [], set()
    for r in rows[i + 1:]:
        ngay = ngay_tu(lay(r, m, "ngày"))
        ma_tre = chu(lay(r, m, "mã trẻ"), 40)
        if not ngay or not ma_tre:
            continue
        k = (ngay, ma_tre)
        if k in thay:
            continue
        thay.add(k)
        out.append({
            "ngay": ngay, "ma_tre": ma_tre,
            "ma_truong": chu(lay(r, m, "mã trường"), 40),
            "ten_truong": chu(lay(r, m, "tên trường"), 120),
            "ten_tre": chu(lay(r, m, "tên trẻ"), 120),
            "lop": chu(lay(r, m, "lớp"), 120),
            "trang_thai": chu(lay(r, m, "trạng thái"), 40),
            "gio_den": gio_tu(lay(r, m, "giờ đến (hh:mm)", "giờ đến")),
            "gio_ve": gio_tu(lay(r, m, "giờ về (hh:mm)", "giờ về")),
            "den_muon": so(lay(r, m, "đến muộn (phút)", "đến muộn")),
            "ve_muon": so(lay(r, m, "về muộn (phút)", "về muộn")),
            "ly_do": chu(lay(r, m, "lý do vắng / ghi chú", "lý do vắng"), 300),
        })
    return out


# ---------- sheet 03 ----------
def boc_dan_thuoc(ws):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    i, td = tim_tieu_de(rows, "Ghi chú từ phụ huynh")
    if i is None:
        return []
    m = cot_map(td)
    out, thay = [], set()
    for r in rows[i + 1:]:
        ngay = ngay_tu(lay(r, m, "ngày"))
        ma_tre = chu(lay(r, m, "mã trẻ"), 40)
        if not ngay or not ma_tre:
            continue
        td_ = chu(lay(r, m, "thời điểm (hh:mm)", "thời điểm"), 20)
        gc = chu(lay(r, m, "ghi chú từ phụ huynh"), 400)
        khoa = hashlib.md5(f"{ngay}|{ma_tre}|{td_}|{gc}".encode()).hexdigest()[:24]
        if khoa in thay:
            continue
        thay.add(khoa)
        out.append({"khoa": khoa, "ngay": ngay, "ma_tre": ma_tre,
                    "ma_truong": chu(lay(r, m, "mã trường"), 40),
                    "ten_truong": chu(lay(r, m, "tên trường"), 120),
                    "ten_tre": chu(lay(r, m, "tên trẻ"), 120),
                    "lop": chu(lay(r, m, "lớp"), 120),
                    "ghi_chu": gc, "thoi_diem": td_,
                    "trang_thai": chu(lay(r, m, "trạng thái"), 40),
                    "nguoi_cho_uong": chu(lay(r, m, "người cho uống"), 120)})
    return out


# ---------- sheet 04 ----------
def boc_gop_y(ws):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    i, td = tim_tieu_de(rows, "Mã góp ý")
    if i is None:
        return []
    m = cot_map(td)
    out, thay = [], set()
    for r in rows[i + 1:]:
        ma = chu(lay(r, m, "mã góp ý"), 60)
        ngay = ngay_tu(lay(r, m, "ngày gửi"))
        if not ma or not ngay:
            continue
        khoa = f"{ngay}_{ma}"
        if khoa in thay:
            continue
        thay.add(khoa)
        out.append({"khoa": khoa, "ma_gop_y": ma, "ngay_gui": ngay,
                    "ma_truong": chu(lay(r, m, "mã trường"), 40),
                    "ten_truong": chu(lay(r, m, "tên trường"), 120),
                    "phu_huynh": chu(lay(r, m, "phụ huynh"), 120),
                    "ma_tre": chu(lay(r, m, "trẻ liên quan (mã)"), 40),
                    "ten_tre": chu(lay(r, m, "trẻ liên quan (tên)"), 120),
                    "lop": chu(lay(r, m, "lớp"), 120),
                    "chu_de": chu(lay(r, m, "chủ đề"), 200),
                    "noi_dung": chu(lay(r, m, "nội dung (rút gọn)", "nội dung"), 800),
                    "trang_thai": chu(lay(r, m, "trạng thái"), 40),
                    "ngay_cap_nhat": ngay_tu(lay(r, m, "ngày cập nhật cuối")),
                    "nguoi_xu_ly": chu(lay(r, m, "người xử lý"), 120)})
    return out


# ---------- sheet 05 ----------
def boc_ticket(ws):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    i, td = tim_tieu_de(rows, "Mã ticket")
    if i is None:
        return []
    m = cot_map(td)
    out, thay = [], set()
    for r in rows[i + 1:]:
        ma = chu(lay(r, m, "mã ticket"), 60)
        if not ma or ma in thay:
            continue
        thay.add(ma)
        out.append({"ma_ticket": ma,
                    "ngay_tao": ngay_tu(lay(r, m, "ngày tạo")),
                    "ma_truong": chu(lay(r, m, "mã trường"), 40),
                    "ten_truong": chu(lay(r, m, "tên trường"), 120),
                    "tieu_de": chu(lay(r, m, "tiêu đề"), 400),
                    "phan_loai": chu(lay(r, m, "phân loại"), 60),
                    "muc_do": chu(lay(r, m, "mức độ"), 40),
                    "trang_thai": chu(lay(r, m, "trạng thái"), 40),
                    "nguoi_tao": chu(lay(r, m, "người tạo"), 120),
                    "nguoi_duoc_giao": chu(lay(r, m, "người được giao"), 120),
                    "so_tre": so(lay(r, m, "số trẻ liên quan")),
                    "ngay_cap_nhat": ngay_tu(lay(r, m, "ngày cập nhật cuối")),
                    "ngay_dong": ngay_tu(lay(r, m, "ngày đóng (nếu có)", "ngày đóng"))})
    return out


# ---------- sheet 06 ----------
def boc_ticket_tre(ws):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    i, td = tim_tieu_de(rows, "Mã ticket")
    if i is None:
        return []
    m = cot_map(td)
    out, thay = [], set()
    for r in rows[i + 1:]:
        ma = chu(lay(r, m, "mã ticket"), 60)
        mt = chu(lay(r, m, "mã trẻ"), 40)
        if not ma or not mt or (ma, mt) in thay:
            continue
        thay.add((ma, mt))
        out.append({"ma_ticket": ma, "ma_tre": mt,
                    "ngay_tao": ngay_tu(lay(r, m, "ngày tạo")),
                    "ma_truong": chu(lay(r, m, "mã trường"), 40),
                    "ten_truong": chu(lay(r, m, "tên trường"), 120),
                    "ten_tre": chu(lay(r, m, "tên trẻ"), 120),
                    "lop": chu(lay(r, m, "lớp"), 120)})
    return out


BOC = [
    ("01", "TỔNG QUAN", None, "tomia_ngay", "ngay,ma_truong"),
    ("02", "Điểm danh", boc_diem_danh, "tomia_diem_danh", "ngay,ma_tre"),
    ("03", "Dặn thuốc", boc_dan_thuoc, "tomia_dan_thuoc", "khoa"),
    ("04", "Góp ý", boc_gop_y, "tomia_gop_y", "khoa"),
    ("05", "Vận hành - Chi tiết", boc_ticket, "tomia_ticket", "ma_ticket"),
    ("06", "Vận hành - Trẻ", boc_ticket_tre, "tomia_ticket_tre", "ma_ticket,ma_tre"),
]


def main():
    teps = danh_sach_tep()
    print(f"Tim thay {len(teps)} tep Tomia")
    tong = {}
    for ten in teps:
        try:
            noi_dung = goi(f"{SB_URL}/storage/v1/object/{BUCKET}/{ten}", raw=True)
            wb = openpyxl.load_workbook(io.BytesIO(noi_dung), read_only=True, data_only=True)
            for so_hieu, moc, ham, bang, xd in BOC:
                ten_sheet = next((s for s in wb.sheetnames
                                  if s.startswith(so_hieu) or moc.lower() in s.lower()), None)
                if not ten_sheet:
                    continue
                ws = wb[ten_sheet]
                dong = boc_tong_quan(ws, ten) if ham is None else ham(ws)
                if dong:
                    ghi(bang, dong, xd)
                    tong[bang] = tong.get(bang, 0) + len(dong)
            wb.close()
            print(f"  {ten}: xong")
        except Exception as e:
            print(f"  {ten}: LOI {type(e).__name__} {e}")
    for k, v in tong.items():
        print(f"Ghi {v} dong vao {k}")

    try:
        print("Don kho:", goi(f"{SB_URL}/rest/v1/rpc/don_kho", "POST", {}))
    except Exception as e:
        print(f"Don kho: LOI {type(e).__name__} {e}")


if __name__ == "__main__":
    main()
