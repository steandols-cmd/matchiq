"""Strömmande läsning av stora JSON-arrayer ([{...}, {...}, ...]) utan att hela filen läses in i minnet."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import IO


def iter_json_array(fp: IO[str], chunk_size: int = 1 << 20) -> Iterator[object]:
    dec = json.JSONDecoder()
    buf = ""
    pos = 0
    started = False
    eof = False

    def fill() -> bool:
        nonlocal buf, pos, eof
        chunk = fp.read(chunk_size)
        if not chunk:
            eof = True
            return False
        buf = buf[pos:] + chunk
        pos = 0
        return True

    while True:
        # hoppa över blanksteg och avgränsare
        while True:
            while pos < len(buf) and buf[pos] in " \t\r\n,":
                pos += 1
            if pos < len(buf) or eof:
                break
            fill()
        if pos >= len(buf):
            if eof:
                if not started:
                    raise ValueError("Ingen JSON-array hittades")
                raise ValueError("JSON-arrayen avslutades inte")
            continue
        ch = buf[pos]
        if not started:
            if ch != "[":
                raise ValueError(f"Förväntade '[' men fick {ch!r}")
            started = True
            pos += 1
            continue
        if ch == "]":
            return
        try:
            obj, end = dec.raw_decode(buf, pos)
        except json.JSONDecodeError:
            if eof or not fill():
                raise
            continue
        # Tal och literaler kan vara avkortade vid buffertgränsen ("1." av "1.5") – kräv en avgränsare efter
        if not isinstance(obj, (dict, list, str)) and not eof and (end >= len(buf) or buf[end] not in " \t\r\n,]"):
            if fill():
                continue
        yield obj
        pos = end
        if pos > chunk_size:
            buf = buf[pos:]
            pos = 0
