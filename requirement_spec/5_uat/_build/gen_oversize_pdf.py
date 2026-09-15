"""Generate a VALID, openable PDF padded to ~11 MB — a mock file for UAT-28
(upload a file larger than the 10 MB cap and confirm the app rejects it).

The page renders one line of text; the bulk is a large PDF comment inside the
content stream, so the file is a real single-page PDF that opens in any reader,
just big. The cross-reference table offsets are computed from the assembled bytes.

    python -X utf8 requirement_spec/5_uat/_build/gen_oversize_pdf.py
Output: requirement_spec/5_uat/test_files/UAT-28-oversize-11MB.pdf
"""
from __future__ import annotations
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "test_files" / "UAT-28-oversize-11MB.pdf"
PAD_BYTES = 11_534_000  # comment padding -> total ~11.0 MiB (Windows shows ~11.0 MB, over the 10 MB cap)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # content stream: a huge single-line comment (%…) then a bit of real drawing
    pad = b" " * PAD_BYTES
    stream = (b"% UAT-28 oversize test file - padding follows\n%" + pad + b"\n"
              b"BT /F1 24 Tf 72 720 Td (UAT-28 oversize test file - about 11 MB) Tj ET\n")

    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")   # binary marker line
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_pos = len(buf)
    n = len(objs) + 1
    buf += f"xref\n0 {n}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (b"trailer\n<< /Size " + str(n).encode() + b" /Root 1 0 R >>\n"
            b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF\n")

    OUT.write_bytes(buf)
    print(f"wrote {OUT}  ({len(buf):,} bytes = {len(buf)/1024/1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
