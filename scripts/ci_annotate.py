"""Visa testfel som GitHub Actions-anteckningar (syns i körningens sammanfattning och via API:t).

    python scripts/ci_annotate.py LOGGFIL [rubrik]

Letar upp unittest-block (ERROR:/FAIL:) och skriver ut dem som ::error-rader. Hittas inga block skrivs
slutet av loggen ut i stället.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_ANNOTATIONS = 9
MAX_CHARS = 3500


def esc(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def esc_prop(s: str) -> str:
    return esc(s).replace(":", "%3A").replace(",", "%2C")


def main() -> None:
    path = Path(sys.argv[1])
    title = sys.argv[2] if len(sys.argv) > 2 else "Testfel"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else f"Loggfilen {path} saknas"
    blocks = re.findall(r"^={20,}\n((?:ERROR|FAIL): .*?)(?=^={20,}|^-{20,}\nRan |\Z)", text, re.S | re.M)
    out = []
    for b in blocks[:MAX_ANNOTATIONS]:
        head, _, body = b.partition("\n")
        body = body.strip("-\n ")
        if len(body) > MAX_CHARS:
            body = "…" + body[-MAX_CHARS:]
        out.append(f"::error title={esc_prop(head[:200])}::{esc(body)}")
    if not out:
        tail = text[-6000:]
        out.append(f"::error title={esc_prop(title)}::{esc(tail)}")
    summary = re.search(r"^(Ran \d+ tests.*?)$\n+^(FAILED.*|OK.*)$", text, re.M)
    if summary:
        out.append(f"::notice title=Sammanfattning::{esc(summary.group(1) + ' – ' + summary.group(2))}")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
