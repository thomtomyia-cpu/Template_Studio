#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
studio_template.py
==================
Generatore di dispense / schede di studio in PDF con uno stile ordinato e pulito:
banner colorato, riquadri con linguetta, intestazione sottile, numerazione
automatica delle sezioni, schema a tappe, riepilogo finale.

Funziona per QUALSIASI materia o scopo (matematica, storia, programmazione,
medicina, lingue, appunti personali, ripasso per esami...).

TEMPLATE
--------
Il template (build_template) apre con una pagina di ISTRUZIONI da eliminare nel documento
finale: spiega che tutti gli elementi sono opzionali e vanno usati solo se servono.
Nei tuoi documenti NON chiamare d.instructions(...).

USO RAPIDO
----------
    pip install reportlab
    python studio_template.py          # genera il template vuoto "Template_Studio.pdf"

USO NEI TUOI DOCUMENTI
----------------------
    from studio_template import StudyDoc

    d = StudyDoc("storia_cap3.pdf",
                 left="Storia moderna", right="Liceo - Classe 4A")
    d.banner("CAPITOLO 3 • UNITA 2", "La Rivoluzione francese",
             "e la domanda: perche scoppio nel 1789?")
    d.goals("Obiettivi.", "capire le cause; ordinare gli eventi; spiegare l'esito.")
    d.h1("Da dove partiamo")
    d.p("Testo normale. Puoi usare <b>grassetto</b>, <i>corsivo</i>, x<super>2</super>, H<sub>2</sub>O.")
    d.definition("Testo della definizione...")
    d.example("Un esempio concreto...")
    d.idea("L'intuizione dietro il concetto...")
    d.warning("L'errore classico da evitare...")
    d.key("La regola o formula chiave...", label="Regola chiave")
    d.callout("Metodo.", "1) primo passo; 2) secondo passo; 3) terzo passo.")
    d.flow(["causa", "evento", "conseguenza"])
    d.summary(["Punto 1.", "Punto 2.", "Punto 3."])
    d.next_up("Prossima unita:", "anteprima di cio che viene dopo.")
    d.closing("Un gradino alla volta. Frase di chiusura.")
    d.build()

NOTE SUL TESTO
--------------
- Dentro i testi puoi usare i tag: <b> <i> <u> <sub> <super> <br/> <font color="#aa0000">.
- I caratteri "&" e "<" semplici vengono gestiti automaticamente.
- Ogni metodo di riquadro accetta una stringa OPPURE una lista di stringhe
  (ogni elemento diventa un paragrafo).
- Per cambiare colori: StudyDoc(..., theme={"primary": "#7a1a3a"}).
"""

import html
import re
import sys

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, HRFlowable, Image, KeepTogether,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    XPreformatted,
)

# --------------------------------------------------------------------------
#  TEMA (colori e font) - modificabile
# --------------------------------------------------------------------------
DEFAULT_THEME = {
    # colore principale (banner, titoli, intestazione)
    "primary": "#1a4d7a",
    "header_text": "#4a76a8",
    "header_rule": "#a3b8ca",
    # riquadro "callout" (obiettivi, metodo, spoiler)
    "callout_bg": "#f1f4f7",
    "callout_border": "#a3b8ca",
    # riquadri con linguetta: (colore linguetta/bordo, sfondo)
    "definition": ("#5b3a99", "#f0ebf8"),
    "example": ("#0e7c7b", "#e5f2f2"),
    "idea": ("#1e7d4f", "#e9f5ee"),
    "warning": ("#b8780f", "#fbf1dd"),
    "key": ("#1a4d7a", "#eaf0f7"),
    "note": ("#5f6b7a", "#f1f3f5"),
    "exercise": ("#b03a48", "#fbecee"),
    "arrow": "#c0392b",
    # font: devono essere font base di reportlab oppure registrati da te
    "font_serif": "Times-Roman",
    "font_serif_bold": "Times-Bold",
    "font_serif_italic": "Times-Italic",
    "font_sans": "Helvetica",
    "font_sans_bold": "Helvetica-Bold",
    "font_mono": "Courier",
}

# Etichette dei riquadri (traducibili / personalizzabili)
DEFAULT_LABELS = {
    "definition": "Definizione",
    "example": "Esempio",
    "idea": "L'idea",
    "warning": "Attenzione",
    "key": "Regola chiave",
    "note": "Nota",
    "exercise": "Esercizio",
    "summary_title": "Cosa ricordare",
}

_ALLOWED_TAGS = r"b|i|u|sub|super|font|br|strike|a|span|strong|em"


def _fix(text):
    """Rende sicuro il testo per il parser di Paragraph (& e < isolati)."""
    text = re.sub(r"&(?!#?\w+;)", "&amp;", text)
    text = re.sub(r"<(?!/?(?:%s)\b)" % _ALLOWED_TAGS, "&lt;", text)
    return text


def _as_list(x):
    return [x] if isinstance(x, str) else list(x)


# --------------------------------------------------------------------------
#  FLOWABLE DI BASE: contenitore con padding e possibilita di spezzarsi
# --------------------------------------------------------------------------
class _Container(Flowable):
    def __init__(self, items, padx=8, pad_top=4, pad_bottom=5, gap=3):
        super().__init__()
        self.items = items
        self.padx, self.pad_top, self.pad_bottom, self.gap = padx, pad_top, pad_bottom, gap
        self.top_inset = 0  # spazio extra sopra il rettangolo (per la linguetta)
        self.hAlign = "LEFT"

    def _clone(self, items, first):  # da ridefinire
        raise NotImplementedError

    def _inner_w(self, aw):
        return aw - 2 * self.padx

    def wrap(self, aw, ah):
        self.aw = aw
        iw = self._inner_w(aw)
        self._hs = [it.wrap(iw, 10 ** 6)[1] for it in self.items]
        body = self.pad_top + sum(self._hs) + self.gap * (len(self.items) - 1) + self.pad_bottom
        self.h = body + self.top_inset
        return aw, self.h

    def split(self, aw, ah):
        iw = self._inner_w(aw)
        avail = ah - self.top_inset - self.pad_top - self.pad_bottom
        if avail <= 0:
            return []
        used, first, rest = 0, [], []
        for idx, it in enumerate(self.items):
            h = it.wrap(iw, 10 ** 6)[1]
            g = self.gap if first else 0
            if used + g + h <= avail:
                first.append(it)
                used += g + h
                continue
            parts = it.split(iw, avail - used - g) if hasattr(it, "split") else []
            if len(parts) == 2:
                first.append(parts[0])
                rest = [parts[1]] + self.items[idx + 1:]
            else:
                rest = self.items[idx:]
            break
        if not first or not rest:
            return []
        return [self._clone(first, True), self._clone(rest, False)]

    def draw_bg(self, c, body_h):
        pass

    def draw(self):
        c = self.canv
        body = self.h - self.top_inset
        self.draw_bg(c, body)
        y = body - self.pad_top
        for it, h in zip(self.items, self._hs):
            y -= h
            it.drawOn(c, self.padx, y)
            y -= self.gap


class Panel(_Container):
    """Rettangolo pieno con bordo opzionale (banner, callout, prossima lezione)."""

    def __init__(self, items, bg, border=None, border_w=0, radius=0,
                 padx=12, pad_top=9, pad_bottom=9, gap=4):
        super().__init__(items, padx, pad_top, pad_bottom, gap)
        self.bg, self.border, self.border_w, self.radius = bg, border, border_w, radius
        self.spaceBefore, self.spaceAfter = 4, 10

    def _clone(self, items, first):
        p = Panel(items, self.bg, self.border, self.border_w, self.radius,
                  self.padx, self.pad_top, self.pad_bottom, self.gap)
        p.spaceBefore, p.spaceAfter = self.spaceBefore, self.spaceAfter
        return p

    def draw_bg(self, c, body):
        c.saveState()
        c.setFillColor(HexColor(self.bg))
        if self.border and self.border_w:
            hw = self.border_w / 2.0
            c.setStrokeColor(HexColor(self.border))
            c.setLineWidth(self.border_w)
            c.roundRect(hw, hw, self.aw - 2 * hw, body - 2 * hw, self.radius, fill=1, stroke=1)
        else:
            c.roundRect(0, 0, self.aw, body, self.radius, fill=1, stroke=0)
        c.restoreState()


class Box(_Container):
    """Riquadro con linguetta colorata sul bordo superiore sinistro."""

    TAB_H = 11.5

    def __init__(self, items, label, fg, bg, font_bold, star=False, first=True):
        super().__init__(items, padx=8, pad_top=4, pad_bottom=5, gap=3)
        self.label, self.fg, self.bg, self.font_bold = label, fg, bg, font_bold
        self.star, self.first = star, first
        self.top_inset = self.TAB_H / 2.0 if first else 0
        self.spaceBefore, self.spaceAfter = 5, 9
        if first:
            self.pad_top = 6

    def _clone(self, items, first):
        b = Box(items, self.label, self.fg, self.bg, self.font_bold, self.star, first=False)
        b.spaceBefore = b.spaceAfter = 0
        return b

    def draw_bg(self, c, body):
        c.saveState()
        c.setFillColor(HexColor(self.bg))
        c.setStrokeColor(HexColor(self.fg))
        c.setLineWidth(0.9)
        c.roundRect(0, 0, self.aw, body, 2, fill=1, stroke=1)
        if self.first:
            fs = 7.8
            tw = stringWidth(self.label, self.font_bold, fs)
            extra = 10 if self.star else 0
            tab_w = tw + extra + 12
            ty = body - self.TAB_H / 2.0
            c.setFillColor(HexColor(self.fg))
            c.roundRect(8, ty, tab_w, self.TAB_H, 1.8, fill=1, stroke=0)
            c.setFillColor(white)
            x = 14
            if self.star:  # stellina disegnata a mano (i font base non hanno il glifo)
                self._star(c, x + 3.2, ty + self.TAB_H / 2.0, 3.4)
                x += extra
            c.setFont(self.font_bold, fs)
            c.drawString(x, ty + 3.4, self.label)
        c.restoreState()

    @staticmethod
    def _star(c, cx, cy, r):
        import math
        p = c.beginPath()
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.42
            x, y = cx + rad * math.cos(ang), cy + rad * math.sin(ang)
            p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
        p.close()
        c.drawPath(p, fill=1, stroke=0)


class Flow(Flowable):
    """Schema a tappe:  [a] -> [b] -> [c]"""

    def __init__(self, steps, color, arrow, font, size=8.2):
        super().__init__()
        self.steps, self.color, self.arrow, self.font, self.size = steps, color, arrow, font, size
        self.bh, self.padx, self.gap = 17, 8, 16
        self.spaceBefore, self.spaceAfter = 6, 12

    def wrap(self, aw, ah):
        self.aw = aw
        self.ws = [stringWidth(s, self.font, self.size) + 2 * self.padx for s in self.steps]
        self.total = sum(self.ws) + self.gap * (len(self.steps) - 1)
        self.k = min(1.0, aw / self.total)
        return aw, self.bh + 4

    def draw(self):
        c = self.canv
        c.saveState()
        c.translate((self.aw - self.total * self.k) / 2.0, 2)
        c.scale(self.k, self.k)
        x = 0
        for i, (s, w) in enumerate(zip(self.steps, self.ws)):
            c.setStrokeColor(HexColor(self.color))
            c.setFillColor(white)
            c.setLineWidth(1.1)
            c.rect(x, 0, w, self.bh, fill=1, stroke=1)
            c.setFillColor(HexColor(self.color))
            c.setFont(self.font, self.size)
            c.drawCentredString(x + w / 2.0, 5.4, s)
            x += w
            if i < len(self.steps) - 1:
                y = self.bh / 2.0
                c.setStrokeColor(HexColor(self.arrow))
                c.setFillColor(HexColor(self.arrow))
                c.setLineWidth(0.8)
                c.line(x + 1.5, y, x + self.gap - 1.5, y)
                p = c.beginPath()
                p.moveTo(x + self.gap - 1, y)
                p.lineTo(x + self.gap - 4.5, y + 2)
                p.lineTo(x + self.gap - 4.5, y - 2)
                p.close()
                c.drawPath(p, fill=1, stroke=0)
                x += self.gap
        c.restoreState()


class BottomNote(Flowable):
    """Frase in corsivo ancorata in fondo alla pagina corrente."""

    def __init__(self, text, font, size=8.5, color="#8a8f96"):
        super().__init__()
        self.text, self.font, self.size, self.color = text, font, size, color

    def wrap(self, aw, ah):
        self.aw, self.ah = aw, max(ah - 1, 12)
        return self.aw, self.ah

    def draw(self):
        c = self.canv
        c.setFillColor(HexColor(self.color))
        c.setFont(self.font, self.size)
        c.drawString(0, 0, self.text)


# --------------------------------------------------------------------------
#  DOCUMENTO
# --------------------------------------------------------------------------
class StudyDoc:
    def __init__(self, filename="documento_studio.pdf", left="Nome della materia",
                 right="Corso di studio", title=None, author="", theme=None, labels=None):
        self.filename = filename
        self.left, self.right = left, right
        self.title, self.author = title or left, author
        self.t = dict(DEFAULT_THEME)
        if theme:
            self.t.update(theme)
        self.L = dict(DEFAULT_LABELS)
        if labels:
            self.L.update(labels)
        self.story = []
        self.cnt = [0, 0, 0]
        self._styles()

    # ---------------- stili ----------------
    def _styles(self):
        t = self.t
        P = t["primary"]
        self.s_body = ParagraphStyle("body", fontName=t["font_serif"], fontSize=10.3,
                                     leading=14, alignment=TA_JUSTIFY, spaceAfter=5,
                                     firstLineIndent=12)
        self.s_box = ParagraphStyle("box", parent=self.s_body, firstLineIndent=0,
                                    spaceAfter=0, fontSize=10, leading=13.2)
        self.s_h1 = ParagraphStyle("h1", fontName=t["font_sans_bold"], fontSize=15.5,
                                   leading=19, textColor=HexColor(P), spaceBefore=14,
                                   spaceAfter=2, keepWithNext=1, leftIndent=0)
        self.s_h2 = ParagraphStyle("h2", fontName=t["font_sans_bold"], fontSize=11.2,
                                   leading=14, textColor=HexColor(P), spaceBefore=8,
                                   spaceAfter=3, keepWithNext=1)
        self.s_h3 = ParagraphStyle("h3", fontName=t["font_sans_bold"], fontSize=9.3,
                                   leading=12, textColor=HexColor("#2b5f8f"), spaceBefore=6,
                                   spaceAfter=2, keepWithNext=1)
        self.s_list = ParagraphStyle("list", parent=self.s_body, firstLineIndent=0,
                                     leftIndent=24, bulletIndent=10, spaceAfter=3.5,
                                     alignment=TA_LEFT, bulletFontName=t["font_serif"])
        self.s_cell = ParagraphStyle("cell", fontName=t["font_serif"], fontSize=9.3,
                                     leading=11.5, alignment=TA_LEFT)
        self.s_cell_h = ParagraphStyle("cellh", fontName=t["font_sans_bold"], fontSize=8.5,
                                       leading=11, textColor=white, alignment=TA_LEFT)
        self.s_cap = ParagraphStyle("cap", fontName=t["font_serif_italic"], fontSize=8.8,
                                    leading=11, alignment=TA_CENTER,
                                    textColor=HexColor("#5f6b7a"), spaceAfter=8)
        self.s_code = ParagraphStyle("code", fontName=t["font_mono"], fontSize=8.6,
                                     leading=11, textColor=HexColor("#22313f"))

    def _par(self, text, style=None):
        return Paragraph(_fix(text), style or self.s_box)

    def _items(self, text):
        return [self._par(x) for x in _as_list(text)]

    # ---------------- testata ----------------
    def banner(self, kicker, title, subtitle=""):
        """Banner colorato iniziale. kicker = riga piccola in alto (es. 'MODULO 1 • LEZIONE 2')."""
        t = self.t
        items = [
            Paragraph(_fix(kicker), ParagraphStyle("k", fontName=t["font_sans"], fontSize=8.2,
                                                   leading=11, textColor=white)),
            Paragraph(_fix(title), ParagraphStyle("bt", fontName=t["font_sans_bold"], fontSize=21,
                                                  leading=26, textColor=white)),
        ]
        if subtitle:
            items.append(Paragraph(_fix(subtitle), ParagraphStyle(
                "bs", fontName=t["font_sans"], fontSize=9.3, leading=12, textColor=HexColor("#dce8f3"))))
        p = Panel(items, t["primary"], padx=14, pad_top=12, pad_bottom=12, gap=3)
        p.spaceBefore, p.spaceAfter = 6, 16
        self.story.append(p)

    def callout(self, lead, text):
        """Riquadro con bordo spesso e parola iniziale in grassetto (obiettivi, metodo, spoiler...)."""
        t = self.t
        txt = '<font name="%s" color="%s">%s</font> %s' % (
            t["font_serif_bold"], t["primary"], _fix(lead), _fix(text))
        sty = ParagraphStyle("co", parent=self.s_box, fontSize=10.2, leading=13.8)
        p = Panel([Paragraph(txt, sty)], t["callout_bg"], t["callout_border"], 2.6, 2.5,
                  padx=13, pad_top=9, pad_bottom=9)
        self.story.append(p)

    goals = callout  # alias: d.goals("Obiettivi.", "...")

    # ---------------- titoli ----------------
    def _num(self, level, numbered):
        if not numbered:
            return ""
        self.cnt[level - 1] += 1
        for i in range(level, 3):
            self.cnt[i] = 0
        return ".".join(str(n) for n in self.cnt[:level]) + " "

    def h1(self, title, numbered=True):
        self.story.append(Paragraph(_fix(self._num(1, numbered) + title), self.s_h1))
        hr = HRFlowable(width="100%", thickness=0.6, color=HexColor("#2a2f36"),
                        spaceBefore=1, spaceAfter=7)
        hr.keepWithNext = 1
        self.story.append(hr)

    def h2(self, title, numbered=True):
        self.story.append(Paragraph(_fix(self._num(2, numbered) + title), self.s_h2))

    def h3(self, title, numbered=True):
        self.story.append(Paragraph(_fix(self._num(3, numbered) + title), self.s_h3))

    # ---------------- testo ----------------
    def p(self, text):
        self.story.append(Paragraph(_fix(text), self.s_body))

    def bullets(self, items):
        for it in items:
            self.story.append(Paragraph(_fix(it), self.s_list, bulletText="\u2022"))
        self.story.append(Spacer(1, 3))

    def numbered(self, items):
        for i, it in enumerate(items, 1):
            self.story.append(Paragraph(_fix(it), self.s_list, bulletText="%d." % i))
        self.story.append(Spacer(1, 3))

    # ---------------- riquadri con linguetta ----------------
    def box(self, kind_or_colors, text, label=None, star=False):
        """kind_or_colors: nome preset ('definition', 'example', ...) oppure ('#colore', '#sfondo')."""
        if isinstance(kind_or_colors, str):
            fg, bg = self.t[kind_or_colors]
            label = label or self.L.get(kind_or_colors, kind_or_colors.title())
        else:
            fg, bg = kind_or_colors
            label = label or ""
        self.story.append(Box(self._items(text), label, fg, bg, self.t["font_sans_bold"], star))

    def definition(self, text, label=None):
        self.box("definition", text, label)

    def example(self, text, label=None):
        self.box("example", text, label)

    def idea(self, text, label=None):
        self.box("idea", text, label, star=True)

    def warning(self, text, label=None):
        self.box("warning", text, label)

    def key(self, text, label=None):
        self.box("key", text, label)

    def note(self, text, label=None):
        self.box("note", text, label)

    def exercise(self, text, label=None):
        self.box("exercise", text, label)

    # ---------------- elementi extra ----------------
    def flow(self, steps):
        """Schema a tappe con frecce."""
        self.story.append(Flow(steps, self.t["primary"], self.t["arrow"], self.t["font_sans"]))

    def table(self, header, rows, col_widths=None):
        """Tabella con intestazione colorata e righe alternate."""
        data = [[Paragraph(_fix(str(h)), self.s_cell_h) for h in header]]
        data += [[Paragraph(_fix(str(c)), self.s_cell) for c in r] for r in rows]
        tb = Table(data, colWidths=col_widths, repeatRows=1, hAlign="CENTER")
        st = [
            ("BACKGROUND", (0, 0), (-1, 0), HexColor(self.t["primary"])),
            ("GRID", (0, 0), (-1, -1), 0.4, HexColor(self.t["callout_border"])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), HexColor(self.t["callout_bg"])))
        tb.setStyle(TableStyle(st))
        self.story += [Spacer(1, 3), tb, Spacer(1, 10)]

    def code(self, text):
        """Blocco di codice / testo a spaziatura fissa."""
        p = Panel([XPreformatted(html.escape(text.strip("\n")), self.s_code)],
                  "#f4f6f8", self.t["callout_border"], 0.6, 2, padx=10, pad_top=7, pad_bottom=7)
        self.story.append(p)

    def image(self, path, width_cm=10, caption=None):
        w, h = ImageReader(path).getSize()
        W = width_cm * cm
        parts = [Image(path, width=W, height=W * h / w)]
        if caption:
            parts.append(Paragraph(_fix(caption), self.s_cap))
        self.story.append(KeepTogether(parts))

    def spacer(self, pts=10):
        self.story.append(Spacer(1, pts))

    def pagebreak(self):
        self.story.append(PageBreak())

    # ---------------- istruzioni (DA RIMUOVERE nel documento finale) ----------------
    def instructions(self, title, lines, legend=None, legend_header=("Elemento", "Quando usarlo")):
        """Pagina di istruzioni all'inizio del template. Va TOLTA nel foglio di studio finale."""
        fg, bg = "#b03a48", "#fdf3f4"
        items = [Paragraph(_fix(x), ParagraphStyle(
            "ins", parent=self.s_box, alignment=TA_LEFT, leftIndent=10, bulletIndent=0,
            spaceAfter=3), bulletText="\u2022") for x in lines]
        self.story.append(Box(items, title, fg, bg, self.t["font_sans_bold"]))
        if legend:
            self.spacer(4)
            self.table(list(legend_header), [list(r) for r in legend], col_widths=[4.6 * cm, 11.6 * cm])
        self.pagebreak()

    # ---------------- chiusura ----------------
    def summary(self, points, title=None):
        """Riepilogo numerato (titolo non numerato)."""
        self.h1(title or self.L["summary_title"], numbered=False)
        self.numbered(points)

    def next_up(self, lead, text):
        """Banner di chiusura con anteprima di cio che viene dopo."""
        t = self.t
        txt = '<font name="%s">%s</font> <font color="#dce8f3">%s</font>' % (
            t["font_sans_bold"], _fix(lead), _fix(text))
        sty = ParagraphStyle("nx", fontName=t["font_serif"], fontSize=10.2, leading=13.8,
                             textColor=white, alignment=TA_LEFT)
        p = Panel([Paragraph(txt, sty)], t["primary"], padx=12, pad_top=9, pad_bottom=9)
        p.spaceBefore, p.spaceAfter = 8, 8
        self.story.append(p)

    def closing(self, text):
        """Frase in corsivo in fondo all'ultima pagina."""
        self.story.append(BottomNote(_plain(text), self.t["font_serif_italic"]))

    # ---------------- costruzione ----------------
    def _on_page(self, canv, doc):
        t = self.t
        w, h = A4
        m = 2.4 * cm
        canv.saveState()
        canv.setFont(t["font_sans"], 8.3)
        canv.setFillColor(HexColor(t["header_text"]))
        y = h - 1.75 * cm
        canv.drawString(m, y, _plain(self.left))
        canv.drawRightString(w - m, y, _plain(self.right))
        canv.setStrokeColor(HexColor(t["header_rule"]))
        canv.setLineWidth(0.5)
        canv.line(m, y - 5, w - m, y - 5)
        canv.setFillColor(HexColor("#8a8f96"))
        canv.setFont(t["font_sans"], 8.3)
        canv.drawRightString(w - m, 1.45 * cm, str(doc.page))
        canv.restoreState()

    def build(self):
        m = 2.4 * cm
        doc = BaseDocTemplate(self.filename, pagesize=A4, leftMargin=m, rightMargin=m,
                              topMargin=2.5 * cm, bottomMargin=2.2 * cm,
                              title=_plain(self.title), author=self.author)
        frame = Frame(m, 2.2 * cm, A4[0] - 2 * m, A4[1] - 4.7 * cm, id="f",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self._on_page)])
        doc.build(self.story)
        return self.filename


def _plain(s):
    """Toglie i tag per i testi disegnati direttamente sul canvas."""
    return html.unescape(re.sub(r"<[^>]+>", "", s))


# --------------------------------------------------------------------------
#  TEMPLATE PRONTO ALL'USO (generico, con segnaposto tra graffe)
# --------------------------------------------------------------------------
INSTRUCTIONS_TITLE = "ISTRUZIONI \u2022 DA RIMUOVERE"

INSTRUCTIONS = [
    "<b>Che cos'\u00e8.</b> Questo \u00e8 un template pronto all'uso, con tutti gli elementi utili per "
    "costruire un riassunto / schema di studio <b>il pi\u00f9 completo possibile</b> sull'argomento "
    "degli appunti condivisi in chat.",
    "<b>Nessun obbligo.</b> Non \u00e8 necessario usare ogni strumento: ogni riquadro, tabella, schema o "
    "sezione va inserito <b>solo se il contenuto lo richiede</b>. Se un elemento non serve, si toglie "
    "senza lasciarne traccia (niente riquadri vuoti o segnaposto).",
    "<b>Obiettivo.</b> Il documento finale deve risultare il pi\u00f9 <b>chiaro, ordinato, gradevole e "
    "semplice</b> da leggere e ripassare possibile.",
    "<b>Completezza.</b> Non omettere nessun concetto presente negli appunti. Mantieni i "
    "<b>termini tecnici e specifici</b> dell'originale, spiegandoli quando serve.",
    "<b>Struttura libera.</b> Titoli, sezioni e ordine vanno adattati all'argomento. Tutto ci\u00f2 che "
    "\u00e8 tra {graffe} \u00e8 un segnaposto da sostituire con il contenuto reale.",
    "<b>Importante.</b> Una volta realizzato il foglio di studio vero e proprio, <b>questa pagina di "
    "istruzioni va eliminata</b>: non deve comparire nel documento finale.",
]

LEGEND = [
    ("Banner + Obiettivi", "In apertura: titolo dell'argomento e cosa si sar\u00e0 in grado di fare/capire."),
    ("Titoli 1 / 1.1 / 1.1.1", "Per organizzare l'argomento in sezioni, sottosezioni e dettagli."),
    ("Definizione", "Definizioni, leggi, teoremi, termini tecnici: una sola idea per riquadro."),
    ("Esempio", "Casi concreti, esempi svolti, casi limite, contro-esempi."),
    ("L'idea", "Intuizione dietro al concetto, motivazione, contesto storico o curiosit\u00e0."),
    ("Attenzione", "Errori comuni, eccezioni, trappole da non dimenticare."),
    ("Regola chiave", "Formula, regola o principio fondamentale da avere sempre presente."),
    ("Riquadro a bordo spesso", "Procedimenti passo-passo, metodi, collegamenti con altri argomenti."),
    ("Schema a tappe", "Sequenze, processi, cronologie, passaggi in ordine."),
    ("Tabelle ed elenchi", "Confronti, classificazioni, dati, elenchi di propriet\u00e0 o casi."),
    ("Nota / Esercizio / Codice", "Solo se davvero utili al contenuto degli appunti."),
    ("Riepilogo finale", "I punti essenziali da ricordare, in poche frasi."),
    ("Anteprima + frase finale", "Solo se ha senso un collegamento con ci\u00f2 che segue."),
]


def build_template(path="Template_Studio.pdf"):
    d = StudyDoc(path, left="{Nome della materia}", right="{Corso / Argomento}",
                 title="Template di studio")

    # ---- Pagina di istruzioni: ELIMINARE nel documento finale ----
    d.instructions(INSTRUCTIONS_TITLE, INSTRUCTIONS, LEGEND)

    # ---- Inizio del foglio di studio ----
    d.banner("{MATERIA} \u2022 {CAPITOLO / ARGOMENTO}", "{Titolo dell'argomento}",
             "{Sottotitolo o domanda guida: facoltativo}")
    d.goals("Obiettivi.", "{Cosa saprai fare o capire alla fine}; {obiettivo 2}; {obiettivo 3}.")

    d.h1("{Introduzione: da dove partiamo}")
    d.p("{Testo d'aggancio: contesto, problema di partenza o ci\u00f2 che si sa gi\u00e0. "
        "Dichiara il punto d'arrivo.}")

    d.h2("{Primo concetto}")
    d.p("{Breve introduzione: a cosa serve, quale problema risolve.}")
    d.definition("{Definizione chiara e rigorosa, in parole semplici. Una sola idea per riquadro.}")
    d.example("{Esempi concreti: casi tipici, casi limite, contro-esempi.}")
    d.idea("{Intuizione dietro al concetto: perch\u00e9 esiste, perch\u00e9 \u00e8 importante, contesto.}")

    d.h3("{Sottoconcetto o caso particolare}")
    d.p("{Dettaglio, eccezione o caso in cui il concetto precedente non basta pi\u00f9.}")
    d.warning("{Errore classico o trappola, con la sua correzione.}")

    d.h1("{Contenuto centrale}")
    d.p("{Qui va il cuore dell'argomento, con tutti i concetti presenti negli appunti.}")
    d.key("{Regola, formula o principio chiave, con una riga di spiegazione.}")
    d.callout("{Nome del metodo}.", "{Procedimento passo-passo: 1) primo passo; 2) secondo passo; "
              "3) terzo passo fino alla conclusione.}")
    d.flow(["{tappa 1}", "{tappa 2}", "{tappa 3}"])

    d.h1("{Altri elementi, solo se servono}")
    d.bullets(["{Elenco puntato: primo punto}", "{secondo punto}", "{terzo punto}"])
    d.table(["{Colonna A}", "{Colonna B}", "{Colonna C}"],
            [["{dato}", "{dato}", "{dato}"], ["{dato}", "{dato}", "{dato}"]])
    d.note("{Nota o promemoria, se necessaria.}")

    d.summary(["{Concetto chiave 1, in una frase.}", "{Concetto chiave 2.}",
               "{Concetto chiave 3.}", "{... tanti punti quanti ne servono.}"])
    d.next_up("{Per proseguire:}", "{Collegamento con l'argomento successivo: facoltativo.}")
    d.closing("{Frase di chiusura breve: facoltativa.}")
    return d.build()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "Template_Studio.pdf"
    print("Creato:", build_template(out))
