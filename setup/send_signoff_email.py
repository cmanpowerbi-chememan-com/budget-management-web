"""
Send sign-off spec docs to reviewer via Microsoft Graph sendMail.

Uses the existing service principal (cman-fabric-write) in .env.
Requires the app to have **Mail.Send (Application)** permission + admin consent.

Run modes:
  python setup/send_signoff_email.py            # PROBE: token + confirm mailbox + check, NO send
  python setup/send_signoff_email.py --send     # actually send

Sender / recipient / files configured below.
"""
import os
import sys
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

TENANT = os.getenv("ENTRA_TENANT_ID")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID")
CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET")

SENDER = "jakkaritw@chememan.com"          # <-- confirm correct
RECIPIENT = "laddawank@chememan.com"

SUBJECT = "ขอความอนุเคราะห์ตรวจเอกสาร Sign-off Spec ระบบ Budget Management Web ก่อนส่งให้ User เซ็นรับรอง"

BODY_HTML = """\
<p>เรียน คุณลัดดาวรรณ</p>
<p>ผมได้จัดทำเอกสาร Sign-off Specification ของระบบ Budget Management Web เสร็จแล้ว จำนวน 7 ฉบับ ตามไฟล์แนบ</p>
<p>รบกวนพี่ช่วยตรวจสอบความถูกต้องและความครบถ้วนของเอกสารก่อนนะครับ
เพื่อที่ผมจะได้ส่งให้ User เซ็นรับรอง (sign-off) เป็นลำดับถัดไป</p>
<p>รายการเอกสารแนบ:</p>
<ol>
  <li>01_main_web_app_spec.docx &mdash; หน้าหลัก / Login &amp; Role</li>
  <li>01_special_gl_subform_spec.docx &mdash; Special GL Subform</li>
  <li>03_edit_gl_group_spec.docx &mdash; แก้ไข GL Group</li>
  <li>07_edit_orgcode_costcenter_spec.docx &mdash; แก้ไข Orgcode / Cost Center</li>
  <li>08_hide_document_number_spec.docx &mdash; ซ่อน Document Number</li>
  <li>09_master_currency_spec.docx &mdash; Master Currency</li>
  <li>10_web_access_submit_data_spec.docx &mdash; Web Access &amp; Submit Data</li>
</ol>
<p>หากมีจุดใดต้องแก้ไขหรือเพิ่มเติม รบกวนแจ้งกลับได้เลยครับ</p>
<p>ขอบคุณครับ<br>Jakkaritw</p>
"""

SPEC_DIR = os.path.join(
    "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec"
)
FILES = [
    "01_main_web_app_spec.docx",
    "01_special_gl_subform_spec.docx",
    "03_edit_gl_group_spec.docx",
    "07_edit_orgcode_costcenter_spec.docx",
    "08_hide_document_number_spec.docx",
    "09_master_currency_spec.docx",
    "10_web_access_submit_data_spec.docx",
]

GRAPH = "https://graph.microsoft.com/v1.0"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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


def confirm_mailbox(token):
    r = requests.get(
        f"{GRAPH}/users/{SENDER}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code == 200:
        u = r.json()
        print(f"[OK] sender mailbox exists: {u.get('displayName')} <{u.get('mail') or u.get('userPrincipalName')}>")
    else:
        # App lacks User.Read.All (only Mail.Send) -> cannot pre-confirm. Not fatal.
        print(f"[WARN] cannot pre-verify mailbox (no dir read): {r.status_code}. "
              f"sendMail will fail loudly if {SENDER} is wrong.")
    return True


def build_attachments():
    atts = []
    for name in FILES:
        path = os.path.join(SPEC_DIR, name)
        if not os.path.exists(path):
            print(f"[FAIL] missing file: {path}")
            sys.exit(1)
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        atts.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": name,
            "contentType": DOCX_MIME,
            "contentBytes": content,
        })
        print(f"  attached: {name} ({len(content)} b64 chars)")
    return atts


def send(token):
    atts = build_attachments()
    msg = {
        "message": {
            "subject": SUBJECT,
            "body": {"contentType": "HTML", "content": BODY_HTML},
            "toRecipients": [{"emailAddress": {"address": RECIPIENT}}],
            "attachments": atts,
        },
        "saveToSentItems": True,
    }
    r = requests.post(
        f"{GRAPH}/users/{SENDER}/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=msg,
        timeout=120,
    )
    if r.status_code == 202:
        print(f"[SENT] -> {RECIPIENT}  (202 Accepted)")
    else:
        print(f"[FAIL] sendMail: {r.status_code} {r.text}")
        sys.exit(1)


def main():
    do_send = "--send" in sys.argv
    print(f"sender   = {SENDER}")
    print(f"recipient= {RECIPIENT}")
    token = get_token()
    print("[OK] token acquired")
    if not confirm_mailbox(token):
        sys.exit(1)
    if do_send:
        send(token)
    else:
        print("[PROBE] dry run only. Re-run with --send to deliver.")


if __name__ == "__main__":
    main()
