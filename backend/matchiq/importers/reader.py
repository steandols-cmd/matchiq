"""Läsning av Excel- och CSV-filer till tabeller, samt inspektion inför import (mappningsvyn).

Inspektionen visar blad, kolumner, antal rader, saknade värden och dubbletter innan något importeras.
"""
from __future__ import annotations

import csv
import hashlib
import io
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import openpyxl

EXCEL_EPOCH = datetime(1899, 12, 30)


@dataclass
class Table:
    name: str
    header_row: int                 # 1-baserat radnummer för rubrikraden
    columns: list[str]
    rows: list[list[Any]] = field(default_factory=list)

    def records(self) -> Iterator[dict[str, Any]]:
        for r in self.rows:
            yield {c: (r[i] if i < len(r) else None) for i, c in enumerate(self.columns)}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stash_copy(src: Path, imports_dir: Path) -> tuple[Path, str]:
    """Kopiera originalfilen till datamappen (namngiven efter hash). Originalet öppnas bara för läsning."""
    digest = file_sha256(src)
    imports_dir.mkdir(parents=True, exist_ok=True)
    dest = imports_dir / f"{digest[:16]}_{src.name}"
    if not dest.exists():
        shutil.copyfile(src, dest)
    return dest, digest


def _is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def detect_header(raw: list[list[Any]], max_scan: int = 25) -> int:
    """Index (0-baserat) för den mest sannolika rubrikraden."""
    best, best_score = 0, -1
    for i, row in enumerate(raw[:max_scan]):
        strings = [v for v in row if isinstance(v, str) and v.strip()]
        filled = [v for v in row if not _is_empty(v)]
        if len(filled) < 2:
            continue
        nxt = raw[i + 1] if i + 1 < len(raw) else []
        nxt_filled = sum(1 for v in nxt if not _is_empty(v))
        score = len(strings) * 2 + (1 if nxt_filled >= len(filled) * 0.5 else 0) - (len(filled) - len(strings))
        if len(strings) == len(filled) and score > best_score:
            best, best_score = i, score
    return best


def _dedupe_columns(cols: list[Any]) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for i, c in enumerate(cols):
        name = str(c).strip() if not _is_empty(c) else f"Kolumn {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out


def read_xlsx(path: Path, sheet: str | None = None, header_row: int | None = None) -> list[Table]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        tables = []
        for ws in wb.worksheets:
            if sheet is not None and ws.title != sheet:
                continue
            raw = [list(r) for r in ws.iter_rows(values_only=True)]
            while raw and all(_is_empty(v) for v in raw[-1]):
                raw.pop()
            if not raw:
                tables.append(Table(ws.title, 1, [], []))
                continue
            h = (header_row - 1) if header_row else detect_header(raw)
            header = raw[h]
            last = max((i for i, v in enumerate(header) if not _is_empty(v)), default=-1)
            width = max(last + 1, 1)
            cols = _dedupe_columns(header[:width])
            rows = [r[:width] + [None] * (width - len(r[:width])) for r in raw[h + 1:]]
            rows = [r for r in rows if not all(_is_empty(v) for v in r)]
            tables.append(Table(ws.title, h + 1, cols, rows))
        return tables
    finally:
        wb.close()


def read_csv(path: Path, header_row: int | None = None) -> list[Table]:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    raw = [row for row in csv.reader(io.StringIO(text), dialect)]
    raw = [[(None if c == "" else _coerce(c)) for c in row] for row in raw]
    if not raw:
        return [Table(path.name, 1, [], [])]
    h = (header_row - 1) if header_row else detect_header(raw)
    cols = _dedupe_columns(raw[h])
    width = len(cols)
    rows = [r[:width] + [None] * (width - len(r[:width])) for r in raw[h + 1:]]
    rows = [r for r in rows if not all(_is_empty(v) for v in r)]
    return [Table(path.name, h + 1, cols, rows)]


def _coerce(v: str) -> Any:
    s = v.strip()
    if s == "":
        return None
    try:
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            # bevara ledande nollor (t.ex. ID "007") som text
            return s if (len(s) > 1 and s.startswith("0")) else int(s)
        if s.count(".") == 1 and s.replace(".", "").replace("-", "").isdigit():
            return float(s)
    except ValueError:
        pass
    return s


def read_any(path: Path, sheet: str | None = None, header_row: int | None = None) -> list[Table]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return read_xlsx(path, sheet, header_row)
    if suffix in (".csv", ".txt", ".tsv"):
        return read_csv(path, header_row)
    raise ValueError(f"Filtypen {suffix} stöds inte (använd .xlsx eller .csv)")


def inspect_tables(tables: list[Table], sample_rows: int = 5) -> list[dict]:
    """Sammanfattning per blad: kolumner, radantal, saknade värden per kolumn, dubblettrader."""
    out = []
    for t in tables:
        missing = {c: 0 for c in t.columns}
        seen: set[tuple] = set()
        dups = 0
        for r in t.rows:
            key = tuple("" if v is None else str(v) for v in r)
            if key in seen:
                dups += 1
            seen.add(key)
            for i, c in enumerate(t.columns):
                if _is_empty(r[i] if i < len(r) else None):
                    missing[c] += 1
        out.append({
            "sheet": t.name,
            "header_row": t.header_row,
            "rows": len(t.rows),
            "columns": [{"name": c, "missing": missing[c],
                         "missing_pct": (missing[c] / len(t.rows) * 100) if t.rows else 0.0} for c in t.columns],
            "duplicate_rows": dups,
            "sample": [[_jsonable(v) for v in r] for r in t.rows[:sample_rows]],
        })
    return out


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (int, float, str)) or v is None:
        return v
    return str(v)


def excel_serial_to_datetime(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        return EXCEL_EPOCH + timedelta(days=float(v))
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y",
                "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.replace(" UTC", "").replace("Z", ""), fmt)
        except ValueError:
            continue
    return None
