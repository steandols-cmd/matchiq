"""PDF-rapport för en fryst prognos (T−30, sen rapport eller test).

Rapporten byggs ENBART från lagrade snapshots – aldrig från en ny beräkning – så att innehållet
alltid motsvarar den frysta prognosen. Saknade värden skrivs som "saknas", aldrig som 0.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from ..config import resource_dir
from ..timeutil import fmt_local, parse_iso, to_stockholm

NAVY = colors.HexColor("#14325C")
NAVY_DARK = colors.HexColor("#0E2443")
LIGHT_BLUE = colors.HexColor("#E3EDF7")
STRIPE = colors.HexColor("#F2F6FB")
BORDER = colors.HexColor("#C9D7E6")
AMBER = colors.HexColor("#F2B233")
AMBER_BG = colors.HexColor("#FFF4DB")
GREEN = colors.HexColor("#2E9E6A")
GREEN_BG = colors.HexColor("#E2F6EC")
RED = colors.HexColor("#C0392B")
GREY = colors.HexColor("#5B6B7F")
HOME_C = colors.HexColor("#1FB57A")
DRAW_C = colors.HexColor("#2F80ED")
AWAY_C = colors.HexColor("#E5B531")

_FONTS_OK = False
WEEKDAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober",
          "november", "december"]
METRIC_NAMES = {"goals": "Mål", "corners": "Hörnor", "shots": "Skott", "sot": "Skott på mål"}


def _fonts() -> None:
    global _FONTS_OK
    if _FONTS_OK:
        return
    fdir = resource_dir() / "assets" / "fonts"
    pdfmetrics.registerFont(TTFont("DejaVu", str(fdir / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fdir / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu",
                                  boldItalic="DejaVu-Bold")
    _FONTS_OK = True


def _styles() -> dict:
    base = dict(fontName="DejaVu", fontSize=8.6, leading=11.2, textColor=colors.HexColor("#1D2733"))
    return {
        "body": ParagraphStyle("body", **base),
        "small": ParagraphStyle("small", **{**base, "fontSize": 7.2, "leading": 9.2, "textColor": GREY}),
        "h1": ParagraphStyle("h1", **{**base, "fontName": "DejaVu-Bold", "fontSize": 17, "leading": 21,
                                      "textColor": NAVY}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": "DejaVu-Bold", "fontSize": 11.5, "leading": 15,
                                      "textColor": NAVY, "spaceBefore": 7, "spaceAfter": 3}),
        "sub": ParagraphStyle("sub", **{**base, "fontSize": 9.5, "leading": 13, "textColor": GREY}),
        "cell": ParagraphStyle("cell", **{**base, "fontSize": 8, "leading": 10}),
        "cellb": ParagraphStyle("cellb", **{**base, "fontName": "DejaVu-Bold", "fontSize": 8, "leading": 10}),
        "head": ParagraphStyle("head", **{**base, "fontName": "DejaVu-Bold", "fontSize": 7.8, "leading": 9.6,
                                          "textColor": colors.white}),
        "flag": ParagraphStyle("flag", **{**base, "fontSize": 7.8, "leading": 10, "alignment": TA_LEFT}),
    }


def long_date(dt) -> str:
    loc = to_stockholm(dt)
    if loc is None:
        return "saknas"
    return f"{WEEKDAYS[loc.weekday()]} {loc.day} {MONTHS[loc.month - 1]} {loc.year} kl. {loc:%H:%M}"


def num(v, digits: int = 2) -> str:
    if v is None:
        return "saknas"
    return f"{v:.{digits}f}".replace(".", ",")


def pct(v) -> str:
    return "saknas" if v is None else f"{v * 100:.1f} %".replace(".", ",")


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.translate(str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "ß": "ss"})))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "lag"


def report_filename(match: dict, kind: str, kickoff_utc: str) -> str:
    loc = to_stockholm(kickoff_utc)
    suffix = {"T-30": "T-30", "late": "SEN", "test": "TEST", "manual": "MANUELL"}.get(kind, kind)
    return (f"{loc:%Y-%m-%d_%H%M}_{match['comp_code']}_{slug(match['home_name'])}_vs_{slug(match['away_name'])}"
            f"_m{match['id']}_{suffix}.pdf")


class ProbBar(Flowable):
    def __init__(self, p: tuple[float, float, float], width: float, height: float = 9 * mm):
        super().__init__()
        self.p, self.width, self.height = p, width, height

    def draw(self):
        c = self.canv
        x = 0.0
        for val, col, lab in zip(self.p, (HOME_C, DRAW_C, AWAY_C), ("1", "X", "2")):
            w = self.width * val
            c.setFillColor(col)
            c.roundRect(x, 0, max(w, 0.1), self.height, 2.2, stroke=0, fill=1)
            if w > 18 * mm:
                c.setFillColor(colors.white)
                c.setFont("DejaVu-Bold", 8.5)
                c.drawString(x + 2.5 * mm, self.height / 2 - 3, f"{lab}  {val * 100:.0f} %")
            x += w


def _table(data, col_widths, header=True, zebra=True, extra=None) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    st = [("FONTNAME", (0, 0), (-1, -1), "DejaVu"), ("FONTSIZE", (0, 0), (-1, -1), 8),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold")]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), STRIPE))
    st += extra or []
    t.setStyle(TableStyle(st))
    return t


def build_report(snapshots: list[dict], out_path: Path, *, kind: str, created_at: datetime,
                 extra_notes: list[str] | None = None) -> Path:
    """snapshots: lista av laddade snapshots (load_snapshot) för samma match och datagräns."""
    _fonts()
    S = _styles()
    by_fam = {s["model_family"]: s for s in snapshots}
    first = snapshots[0]
    pl = first["payload"]
    match = pl["match"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=24 * mm, bottomMargin=16 * mm,
                            title=f"MatchIQ prognos {match['home_name']} – {match['away_name']}",
                            author="MatchIQ", subject="Förmatchsprognos")
    W = A4[0] - 28 * mm
    kind_label = {"T-30": "T−30-RAPPORT", "late": "SEN RAPPORT – MISSAD DEADLINE", "test": "TESTRAPPORT",
                  "manual": "MANUELL PROGNOS"}.get(kind, kind)
    simulated = any(s.get("clock") == "simulated" for s in snapshots)
    if simulated:
        kind_label += " · SIMULERAD KLOCKA"
    kickoff = parse_iso(match["kickoff_utc"])
    cutoff = parse_iso(first["data_cutoff_utc"])
    story: list = []

    story.append(Paragraph(f"{match['home_name']} – {match['away_name']}", S["h1"]))
    md = " · ".join(x for x in [match.get("comp_name"), match.get("season"), match.get("matchday")] if x)
    story.append(Paragraph(f"{md} · avspark {long_date(kickoff)} (svensk tid)", S["sub"]))
    story.append(Spacer(1, 4 * mm))

    mins_before = (kickoff - created_at).total_seconds() / 60  # type: ignore[operator]
    if kind == "late":
        timing = f"<font color='#C0392B'><b>SEN</b></font> – skapad {abs(mins_before):.0f} min " + \
                 ("före" if mins_before >= 0 else "efter") + " avspark"
    elif kind == "test":
        timing = "Test – simulerad klocka" if first.get("clock") == "simulated" else "Test"
    else:
        timing = f"I tid – {mins_before:.0f} min före avspark"
    if simulated:
        timing += "<br/><font size=7 color='#7A5AF8'>Skapad med simulerad klocka (test av T−30-flödet)</font>"
    boxes = [
        [Paragraph("<b>Rapport skapad</b>", S["cell"]), Paragraph("<b>Datagräns (cutoff)</b>", S["cell"]),
         Paragraph("<b>Avspark</b>", S["cell"]), Paragraph("<b>Tidsstatus</b>", S["cell"])],
        [Paragraph(f"{fmt_local(created_at)}<br/><font size=7 color='#5B6B7F'>{created_at:%Y-%m-%d %H:%M} UTC"
                   f"</font>", S["cell"]),
         Paragraph(f"{fmt_local(cutoff)}<br/><font size=7 color='#5B6B7F'>{cutoff:%Y-%m-%d %H:%M} UTC</font>",
                   S["cell"]),
         Paragraph(f"{fmt_local(kickoff)}<br/><font size=7 color='#5B6B7F'>{kickoff:%Y-%m-%d %H:%M} UTC</font>",
                   S["cell"]),
         Paragraph(timing + ("" if first["prematch_eligible"] else
                             "<br/><font size=7 color='#C0392B'>Ej behörig för förmatchsutvärdering</font>"),
                   S["cell"])]]
    story.append(_table(boxes, [W / 4] * 4, header=False, zebra=False,
                        extra=[("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE), ("GRID", (0, 0), (-1, -1), 0.6,
                                                                            colors.white)]))
    story.append(Spacer(1, 3 * mm))

    # ---- 1X2
    story.append(Paragraph("1X2-sannolikheter (90 minuter)", S["h2"]))
    rows = [["Modell", "Status", "1 (hemma)", "X", "2 (borta)", "Summa", "Rättvisa odds 1 · X · 2"]]
    fam_style = []
    order = [f for f in ("V2", "V3", "BASE") if f in by_fam]
    for i, fam in enumerate(order, start=1):
        sn = by_fam[fam]
        m = sn["payload"]["model"]
        status = m.get("status") or ""
        label = {"V2": "V2 · jämförelsebaslinje", "V3": "V3 · EXPERIMENTELL", "BASE": "Baslinje (frekvens)"}[fam]
        if fam == "V3" and status == "produktion":
            label = "V3 · produktion"
        ph, px, pa = sn["p_home"], sn["p_draw"], sn["p_away"]
        s = None if ph is None else ph + px + pa
        fair = "saknas" if ph is None else " · ".join(num(1 / p) if p else "–" for p in (ph, px, pa))
        rows.append([Paragraph(f"<b>{label}</b><br/><font size=6.5 color='#5B6B7F'>{sn['model_version_id']}</font>",
                               S["cell"]), status, pct(ph), pct(px), pct(pa),
                     "saknas" if s is None else f"{s * 100:.1f} %".replace(".", ","), fair])
        bg = AMBER_BG if fam == "V2" else (GREEN_BG if fam == "V3" else None)
        if bg:
            fam_style.append(("BACKGROUND", (0, i), (0, i), bg))
    story.append(_table(rows, [42 * mm, 22 * mm, 20 * mm, 17 * mm, 20 * mm, 17 * mm, W - 138 * mm],
                        extra=fam_style))
    for fam in ("V2", "V3"):
        sn = by_fam.get(fam)
        if sn and sn["p_home"] is not None:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(f"<font size=7.5 color='#5B6B7F'>{fam}</font>", S["small"]))
            story.append(ProbBar((sn["p_home"], sn["p_draw"], sn["p_away"]), W))
    story.append(Paragraph("Sannolikheterna summerar till 100 % (avrundade värden kan avvika ±0,1). "
                           "Rättvist odds = 1 / sannolikhet, utan marginal.", S["small"]))

    # ---- förväntade värden
    story.append(Paragraph("Förväntade värden med 80 %-intervall (P10–P90)", S["h2"]))
    for fam in order:
        sn = by_fam[fam]
        mets = sn["payload"]["model"].get("metrics") or {}
        data = [[f"{fam} – mått", f"{match['home_name']}", f"{match['away_name']}", "Totalt", "Fördelning"]]
        for key in ("goals", "corners", "shots", "sot"):
            blk = mets.get(key)
            if blk is None:
                data.append([METRIC_NAMES[key], "saknas", "saknas", "saknas", "spärrad/otillräcklig data"])
                continue
            cell = lambda b: f"{num(b['mean'])}  [{b['lo']}–{b['hi']}]"  # noqa: E731
            data.append([METRIC_NAMES[key], cell(blk["home"]), cell(blk["away"]), cell(blk["total"]),
                         "neg. binomial" if blk["home"].get("dist") == "negbin" else "Poisson"])
        ex = (mets.get("goals") or {}).get("extras") or {}
        if ex.get("btts") is not None:
            data.append(["Båda lagen gör mål", pct(ex.get("btts")), "", f"Över 2,5 mål: {pct(ex.get('over_2_5'))}",
                         f"Troligast: {ex['most_likely_score'][0]}–{ex['most_likely_score'][1]}"])
        story.append(KeepTogether([_table(data, [32 * mm, 37 * mm, 37 * mm, 37 * mm, W - 143 * mm],
                                          extra=[("BACKGROUND", (0, 0), (0, 0),
                                                  AMBER if fam == "V2" else (GREEN if fam == "V3" else NAVY))]),
                                   Spacer(1, 2.5 * mm)]))

    # ---- startelvor
    lus = pl["lineups"]
    lrow = [[f"{match['home_name']}", f"{match['away_name']}"]]
    cells = []
    for side in ("home", "away"):
        lu = lus[side]
        color = {"confirmed": "#2E9E6A", "expected": "#B7791F", "unpublished": "#C0392B"}[lu["status"]]
        txt = f"<font color='{color}'><b>{lu['label']}</b></font>"
        if lu.get("source"):
            txt += f"<br/><font size=7 color='#5B6B7F'>Källa: {lu['source']}; sedd {fmt_local(lu['fetched_at_utc'])}" \
                   f"{'; publicerad ' + fmt_local(lu['published_at_utc']) if lu.get('published_at_utc') else ''}</font>"
        if lu["players"]:
            txt += "<br/>" + "<br/>".join(
                f"{p['number'] if p.get('number') is not None else '·'}  {p['name']}"
                f"{' – ' + p['position'] if p.get('position') else ''}" for p in lu["players"])
        else:
            txt += f"<br/><font size=7.5>{lu.get('note') or 'Ingen elva publicerad.'} Ingen spelarstatus har " \
                   f"antagits.</font>"
        abs_ = pl["absences"][side]
        if abs_:
            kinds = {"injury": "ute", "suspension": "avstängd", "doubtful": "tveksam", "other": "övrigt"}
            txt += "<br/><font size=7 color='#5B6B7F'>Frånvaro: " + "; ".join(
                f"{a['player_name']} ({kinds.get(a['kind'], a['kind'])})" for a in abs_) + "</font>"
        cells.append(Paragraph(txt, S["cell"]))
    lrow.append(cells)
    story.append(KeepTogether([Paragraph("Startelvor vid datagränsen", S["h2"]),
                               _table(lrow, [W / 2, W / 2], zebra=False)]))

    # ---- datatäckning
    story.append(Paragraph("Datatäckning (träningsdata före datagränsen)", S["h2"]))
    cov_rows = [[Paragraph(h, S["head"]) for h in ("Mått", "Matcher i tävlingen", f"{match['home_name']} (V2-fönster)",
                                                     f"{match['away_name']} (V2-fönster)", "Status",
                                                     "Källor (antal matcher)")]]
    v2cov = (by_fam.get("V2") or first)["payload"]["model"].get("coverage", {})
    for key in ("goals", "corners", "shots", "sot"):
        cv = v2cov.get(key) or {}
        used = pl.get("sources_used", {}).get(key) or {}
        cov_rows.append([METRIC_NAMES[key], str(cv.get("league_n", "saknas")),
                         "saknas" if cv.get("home_n") is None else str(cv.get("home_n")),
                         "saknas" if cv.get("away_n") is None else str(cv.get("away_n")),
                         cv.get("status", "saknas"),
                         ", ".join(f"{k}: {v}" for k, v in used.items()) or "ingen tillåten källa"])
    story.append(_table(cov_rows, [24 * mm, 25 * mm, 33 * mm, 33 * mm, 20 * mm, W - 135 * mm]))

    # ---- flaggor
    flags = pl.get("flags") or []
    story.append(Paragraph("Osäkerhetsflaggor", S["h2"]))
    if flags or extra_notes:
        frows = [[Paragraph(("⚠ " if f["level"] == "warning" else "• ") + f["text"], S["flag"])] for f in flags]
        frows += [[Paragraph("⚠ " + n, S["flag"])] for n in (extra_notes or [])]
        story.append(_table(frows, [W], header=False))
    else:
        story.append(Paragraph("Inga särskilda flaggor.", S["body"]))

    # ---- källor och modeller
    story.append(Paragraph("Källor, licenser och modellversioner", S["h2"]))
    src_txt = "<b>Träningsdata från:</b> " + (", ".join(pl.get("training_sources") or []) or "ingen")
    for t in pl.get("training_detail") or []:
        if t.get("policy") != "allowed" and t.get("approval_note"):
            src_txt += (f"<br/><font color='#B7791F'>{t['name']}: används efter användarens dokumenterade beslut "
                        f"({fmt_local(t.get('approved_at_utc'))}) – ”{t['approval_note']}”</font>")
    if pl.get("blocked_sources"):
        src_txt += "<br/><b>Spärrade från träning:</b> " + "; ".join(
            f"{b['name']} – {b['reason']}" for b in pl["blocked_sources"])
    story.append(Paragraph(src_txt, S["cell"]))
    story.append(Spacer(1, 1.5 * mm))
    mrows = [["Modell", "Version", "Status", "Snapshot-ID", "Parametrar"]]
    for fam in order:
        sn = by_fam[fam]
        m = sn["payload"]["model"]
        prm = {k: v for k, v in (m.get("params") or {}).items() if k not in ("selected_on", "selected_at_utc")}
        mrows.append([fam, sn["model_version_id"], m.get("status") or "", Paragraph(
            f"<font size=6.3>{sn['id']}</font>", S["cell"]), Paragraph(
            f"<font size=6.3>{json.dumps(prm, ensure_ascii=False)[:180]}</font>", S["cell"])])
    story.append(_table(mrows, [14 * mm, 20 * mm, 22 * mm, 52 * mm, W - 108 * mm]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "<b>Viktigt:</b> Detta är en statistisk prognos, inte ett löfte om utfall. V3 är experimentell tills den "
        "klarat tidsordnad validering och minst 200 frysta förmatchsprognoser per mått. Prognosen är fryst vid "
        "datagränsen och skrivs aldrig om med efterhandsinformation.", S["small"]))

    def on_page(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(NAVY_DARK)
        canvas.rect(0, A4[1] - 16 * mm, A4[0], 16 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("DejaVu-Bold", 13)
        canvas.drawString(14 * mm, A4[1] - 10.5 * mm, "MATCH")
        canvas.setFillColor(colors.HexColor("#33D69F"))
        canvas.drawString(14 * mm + pdfmetrics.stringWidth("MATCH", "DejaVu-Bold", 13), A4[1] - 10.5 * mm, "IQ")
        canvas.setFillColor(colors.white)
        canvas.setFont("DejaVu", 8.5)
        canvas.drawString(40 * mm, A4[1] - 10.3 * mm, "Förmatchsprognos")
        tag_color = {"late": RED, "test": colors.HexColor("#7A5AF8")}.get(kind, colors.HexColor("#33D69F"))
        canvas.setFillColor(tag_color)
        tw = pdfmetrics.stringWidth(kind_label, "DejaVu-Bold", 8) + 8 * mm
        canvas.roundRect(A4[0] - 14 * mm - tw, A4[1] - 12.5 * mm, tw, 6.5 * mm, 2, stroke=0, fill=1)
        canvas.setFillColor(colors.white if kind != "T-30" else NAVY_DARK)
        canvas.setFont("DejaVu-Bold", 8)
        canvas.drawCentredString(A4[0] - 14 * mm - tw / 2, A4[1] - 10.4 * mm, kind_label)
        canvas.setStrokeColor(BORDER)
        canvas.line(14 * mm, 11 * mm, A4[0] - 14 * mm, 11 * mm)
        canvas.setFillColor(GREY)
        canvas.setFont("DejaVu", 6.8)
        canvas.drawString(14 * mm, 7 * mm, f"MatchIQ · {match['home_name']} – {match['away_name']} · "
                                           f"skapad {fmt_local(created_at)} · statistisk prognos, inte ett löfte om utfall")
        canvas.drawRightString(A4[0] - 14 * mm, 7 * mm, f"Sida {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return out_path
