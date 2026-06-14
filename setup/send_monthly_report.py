"""
Send Budget Management Web monthly progress report via Microsoft Graph sendMail.

Uses the existing service principal (cman-fabric-write) in .env (Mail.Send app perm).

Run modes:
  python setup/send_monthly_report.py          # PROBE: token + build draft, NO send
  python setup/send_monthly_report.py --send    # actually send

Body embeds the report PNG inline (cid) AND attaches the HTML one-pager.
"""
import os
import sys
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TENANT = os.getenv("ENTRA_TENANT_ID")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID")
CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET")

SENDER = "jakkaritw@chememan.com"
RECIPIENT = "pornthipp@chememan.com"
CC = ["laddawank@chememan.com"]

SUBJECT = "รายงานความคืบหน้าโครงการ Budget Management Web (ประจำเดือน มิ.ย. 2026)"

# inline image referenced by cid below
IMG_CID = "monthlyreport"

BODY_HTML = f"""\
<p>เรียน คุณพรทิพย์</p>
<p>ตามที่ขอทราบความคืบหน้าของโครงการ Budget Management Web&nbsp;
ผมขอรายงานสรุปความคืบหน้าประจำเดือน (Monthly Report) ตามภาพด้านล่าง
และไฟล์แนบครับ</p>
<p><img src="cid:{IMG_CID}" style="width:100%;max-width:980px;border:1px solid #ccc;"></p>
<p>สรุปสถานะ: <b>On plan</b> &nbsp;|&nbsp; ความคืบหน้า <b>30%</b> &nbsp;|&nbsp;
เป้าหมาย go-live (ระยะที่ 1: ฟอร์มกรอกงบ + workflow อนุมัติ) <b>สิ้นเดือน ส.ค. 2026</b>
&nbsp;(Dashboard เป็นระยะที่ 2)</p>
<p>รายละเอียดทั้งหมดดูได้จากไฟล์แนบ <b>monthly_report_2026-06.html</b>
(เปิดด้วย browser)</p>
<p>หากมีข้อสงสัยหรือต้องการข้อมูลเพิ่มเติม รบกวนแจ้งกลับได้เลยครับ</p>
<p>ขอบคุณครับ<br>Jakkaritw</p>
"""

DOCS_DIR = "docs"
PNG_FILE = "monthly_report_2026-06.png"
HTML_FILE = "monthly_report_2026-06.html"

GRAPH = "https://graph.microsoft.com/v1.0"


def get_token():
    url = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    r = requests.post(url, data=data, timeout=30)
    if r.status_code != 200:
        print(f"[FAIL] token: {r.status_code} {r.text}")
        sys.exit(1)
    return r.json()["access_token"]


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def build_attachments():
    png_path = os.path.join(DOCS_DIR, PNG_FILE)
    html_path = os.path.join(DOCS_DIR, HTML_FILE)
    for p in (png_path, html_path):
        if not os.path.exists(p):
            print(f"[FAIL] missing file: {p}")
            sys.exit(1)
    atts = [
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": PNG_FILE,
            "contentType": "image/png",
            "contentBytes": _b64(png_path),
            "contentId": IMG_CID,
            "isInline": True,
        },
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": HTML_FILE,
            "contentType": "text/html",
            "contentBytes": _b64(html_path),
        },
    ]
    print(f"  inline image: {PNG_FILE} (cid={IMG_CID})")
    print(f"  attached    : {HTML_FILE}")
    return atts


def build_message():
    return {
        "message": {
            "subject": SUBJECT,
            "body": {"contentType": "HTML", "content": BODY_HTML},
            "toRecipients": [{"emailAddress": {"address": RECIPIENT}}],
            "ccRecipients": [{"emailAddress": {"address": c}} for c in CC],
            "attachments": build_attachments(),
        },
        "saveToSentItems": True,
    }


def send(token):
    msg = build_message()
    r = requests.post(
        f"{GRAPH}/users/{SENDER}/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=msg,
        timeout=180,
    )
    if r.status_code == 202:
        print(f"[SENT] -> {RECIPIENT}  cc={CC}  (202 Accepted)")
    else:
        print(f"[FAIL] sendMail: {r.status_code} {r.text}")
        sys.exit(1)


def main():
    do_send = "--send" in sys.argv
    print(f"sender    = {SENDER}")
    print(f"recipient = {RECIPIENT}")
    print(f"cc        = {CC}")
    print(f"subject   = {SUBJECT}")
    token = get_token()
    print("[OK] token acquired")
    build_attachments()  # validate files exist + print
    if do_send:
        send(token)
    else:
        print("[PROBE] dry run only. Re-run with --send to deliver.")


if __name__ == "__main__":
    main()
