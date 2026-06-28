#!/usr/bin/env python3
"""Render tracker/pending.json -> tracker/PENDING.html (human view).

Source of truth = pending.json (AI reads/writes this).
This script deterministically renders the pretty HTML humans open.
Run after every pending.json change:  python tracker/render_pending.py
"""
import json, os, html, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "pending.json")
OUT = os.path.join(HERE, "PENDING.html")

STATE = {
    "doing":  ("● DOING",   "#f59e0b", "#3b2f1c"),
    "willdo": ("○ WILL DO", "#3b82f6", "#1c2740"),
    "done":   ("✓ DONE",    "#22c55e", "#16271c"),
}
ORDER = ["doing", "willdo", "done"]


def esc(s):
    return html.escape(str(s or ""))


def fmt(iso):
    """ISO -> human, e.g. '28 June 2026 7:23 PM'. Falls back to raw on parse error."""
    if not iso:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return esc(iso)
    h = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.day} {dt.strftime('%B')} {dt.year} {h}:{dt.minute:02d} {ampm}"


def fileurl(p):
    p2 = p.replace("\\", "/")
    return ("file:///" + p2) if os.path.isabs(p) else p2


def files_row(t):
    out = []
    for f in t.get("files", []) or []:
        path = f.get("path", "")
        if not path:
            continue
        check = path if os.path.isabs(path) else os.path.join(HERE, path)
        if not os.path.exists(check):
            continue  # "if exist" — skip missing
        label = f.get("label") or os.path.basename(path)
        out.append(f'<a href="{fileurl(path)}" target="_blank">📎 {esc(label)}</a>')
    return f'<div class="files">{"".join(out)}</div>' if out else ""


def card(t, latest=False):
    label, fg, bg = STATE.get(t.get("state", "willdo"), STATE["willdo"])
    created = fmt(t.get("created", ""))
    updated = fmt(t.get("updated", ""))
    dt = created if created == updated else f"{created} &rarr; {updated}"
    tid = esc(t.get("id", ""))
    agent = esc(t.get("agent", ""))
    skills = t.get("skills", []) or []
    skill_tags = "".join(f'<span class="tag skill">🧩 {esc(s)}</span>' for s in skills)
    who = ""
    if agent or skills:
        atag = f'<span class="tag agent">🤖 {agent}</span>' if agent else ""
        who = f'<div class="who">{atag}{skill_tags}</div>'
    cls = "card latest" if latest else "card"
    newest = '<span class="newest">✨ ล่าสุด</span>' if latest else ""
    return f"""
    <div class="{cls}" data-state="{esc(t.get('state','willdo'))}" style="border-left:4px solid {fg}">
      <div class="top">
        <span class="badge" style="color:{fg};background:{bg};border-color:{fg}55">{label}</span>
        {newest}
        <span class="ref" title="อ้างอิง task นี้เวลาคุยกับ CC">#{tid}</span>
        <span class="dt">{dt}</span>
      </div>
      <div class="id">{tid}</div>
      {who}
      <div class="block ai"><span class="lbl">🤖 AI</span><code>{esc(t.get('ai',''))}</code></div>
      <div class="block hu"><span class="lbl">👤 คน</span><span>{esc(t.get('human',''))}</span></div>
      {files_row(t)}
    </div>"""


def main():
    with open(SRC, encoding="utf-8") as f:
        d = json.load(f)
    tasks = d.get("tasks", [])
    counts = {s: sum(1 for t in tasks if t.get("state") == s) for s in ORDER}
    # primary: state group (doing -> willdo -> done); secondary: updated desc (ISO sorts lexically)
    tasks_sorted = sorted(tasks, key=lambda t: t.get("updated", ""), reverse=True)
    tasks_sorted = sorted(tasks_sorted, key=lambda t: ORDER.index(t.get("state", "willdo")))
    rendered = fmt(datetime.datetime.now().isoformat())

    total = len(tasks)
    latest_id = max(tasks, key=lambda t: t.get("updated", "")).get("id") if tasks else None
    fbtns = f'<button class="fbtn active" data-f="all">ทั้งหมด ({total})</button>'
    fbtns += "".join(
        f'<button class="fbtn" data-f="{s}" style="color:{STATE[s][1]}">{STATE[s][0]}: {counts[s]}</button>'
        for s in ORDER
    )
    body = "\n".join(card(t, latest=(t.get("id") == latest_id)) for t in tasks_sorted)

    htmlout = f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PENDING — {esc(d.get('project',''))}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:"Segoe UI","Leelawadee UI","Tahoma",sans-serif;background:#0f172a;color:#e2e8f0;padding:28px;max-width:1100px;margin:0 auto}}
  h1{{font-size:24px;color:#f8fafc}}
  .meta{{font-size:13px;color:#94a3b8;margin:4px 0 14px}}
  .chips{{display:flex;gap:16px;margin-bottom:22px;font-size:14px;font-weight:600}}
  .card{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:14px 16px;margin-bottom:13px}}
  .top{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .badge{{font-size:12px;font-weight:700;border:1px solid;border-radius:6px;padding:3px 10px}}
  .ref{{margin-right:auto;font-family:Consolas,monospace;font-size:12px;color:#cbd5e1;background:#0f172a;border:1px solid #475569;border-radius:6px;padding:2px 8px}}
  .dt{{font-size:11.5px;color:#64748b;font-family:Consolas,monospace}}
  .id{{font-family:Consolas,monospace;font-size:15px;color:#f1f5f9;margin-bottom:8px}}
  .who{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}}
  .tag{{font-size:11px;border-radius:6px;padding:2px 8px;border:1px solid}}
  .tag.agent{{color:#fbbf24;border-color:#fbbf2455;background:#2a230f}}
  .tag.skill{{color:#67e8f9;border-color:#67e8f955;background:#0c2a30}}
  .block{{display:flex;gap:9px;font-size:13px;line-height:1.6;padding:7px 0}}
  .block .lbl{{flex:0 0 52px;font-size:11px;font-weight:700;color:#94a3b8;padding-top:2px}}
  .block.ai code{{display:block;background:#0f172a;border:1px solid #2d3a4f;border-radius:7px;padding:8px 10px;color:#a5b4fc;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap}}
  .block.hu span{{color:#e2e8f0}}
  .files{{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 2px 61px}}
  .files a{{font-size:12px;color:#f9a8d4;text-decoration:none;background:#2a1020;border:1px solid #be185d;border-radius:6px;padding:3px 9px}}
  .files a:hover{{background:#3a1530;color:#fbcfe8}}
  .newest{{font-size:11px;font-weight:700;color:#fde68a;background:#3b2f0f;border:1px solid #f59e0b88;border-radius:6px;padding:2px 8px}}
  .card>*{{position:relative;z-index:1}}
  .card.latest{{position:relative;border-color:#f59e0b;background:linear-gradient(120deg,#1e293b 0%,#2a3550 45%,#1e293b 90%);overflow:hidden;animation:glow 2.4s ease-in-out infinite}}
  .card.latest::before{{content:"";position:absolute;top:0;left:-70%;width:55%;height:100%;background:linear-gradient(100deg,transparent,rgba(255,255,255,.20),transparent);transform:skewX(-18deg);animation:shine 2.8s ease-in-out infinite;z-index:2;pointer-events:none}}
  @keyframes shine{{0%{{left:-70%}}55%{{left:130%}}100%{{left:130%}}}}
  @keyframes glow{{0%,100%{{box-shadow:inset 0 0 0 2px #f59e0b55}}50%{{box-shadow:inset 0 0 0 2px #f59e0bdd}}}}
  .filters{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:22px}}
  .fbtn{{font-family:inherit;font-size:13.5px;font-weight:600;color:#cbd5e1;background:#1e293b;border:1px solid #334155;border-radius:8px;padding:6px 13px;cursor:pointer}}
  .fbtn:hover{{border-color:#64748b}}
  .fbtn.active{{background:#334155;border-color:#94a3b8;color:#f8fafc}}
</style></head><body>
  <h1>📋 PENDING — {esc(d.get('title',''))}</h1>
  <div class="meta">project: <b>{esc(d.get('project',''))}</b> &bull; updated: {fmt(d.get('updated',''))} &bull; rendered: {rendered}</div>
  <div class="filters">{fbtns}</div>
  {body}
  <div class="meta" style="margin-top:18px">
    อ้างอิง task เวลาคุยกับ CC: พิมพ์ <code>#&lt;id&gt;</code> เช่น <code>#phase2-agents</code><br>
    source of truth: <code>tracker/pending.json</code> — AI อ่านไฟล์นี้ก่อนทำงานทุกครั้ง แล้วอัปเดต state เสมอ. แก้ json แล้วรัน <code>python tracker/render_pending.py</code>
  </div>
  <script>
    const btns = document.querySelectorAll('.fbtn');
    btns.forEach(b => b.addEventListener('click', () => {{
      btns.forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      const f = b.dataset.f;
      document.querySelectorAll('.card').forEach(c => {{
        c.style.display = (f === 'all' || c.dataset.state === f) ? '' : 'none';
      }});
    }}));
  </script>
</body></html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(htmlout)
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
