"""Renders a document from app/services/documents.py to an A4 PDF.

Uses reportlab's built-in Helvetica (no font files to ship); it has no
rupee glyph, so amounts print as "Rs." - standard on Indian invoices.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MAROON = colors.HexColor("#5C1A21")
LINE = colors.HexColor("#E1D2B8")
STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=STYLES["Normal"], fontSize=8.5, leading=11)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#5A453D"))
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)
TITLE = ParagraphStyle("title", parent=STYLES["Title"], fontSize=16, leading=19, textColor=MAROON, alignment=0, spaceAfter=0)


def rs(value) -> str:
    return f"Rs. {value:,.2f}"


def _p(text, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _party(title: str, party: dict, extra: list[str]) -> list:
    rows = [f"<b>{escape(title)}</b>", f"<b>{escape(party.get('name') or '')}</b>"]
    for value in [party.get("address"), *extra]:
        if value:
            rows.append(escape(str(value)).replace("\n", "<br/>"))
    return [Paragraph("<br/>".join(rows), BODY)]


def render(doc: dict) -> bytes:
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"{doc['title']} {doc['number']}", author=doc["seller"]["name"])
    story = []

    header = [[Paragraph(escape(doc["title"]), TITLE), Paragraph(
        f"<b>No.</b> {escape(doc['number'] or '')}<br/><b>Date</b> {escape(doc['date'] or '')}"
        + (f"<br/><b>Against invoice</b> {escape(doc['against']['number'] or '')} ({escape(doc['against']['date'] or '')})" if doc.get("against") else ""),
        RIGHT)]]
    t = Table(header, colWidths=[90 * mm, 92 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1, MAROON), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [t, Spacer(1, 5 * mm)]

    s, b = doc["seller"], doc["buyer"]
    seller_extra = [f"State: {s['state']}" if s.get("state") else None, f"GSTIN: {s['gstin']}" if s.get("gstin") else None,
                    " · ".join(x for x in (s.get("email"), s.get("phone")) if x) or None]
    buyer_extra = [" - ".join(x for x in (b.get("state"), b.get("pincode")) if x) or None, b.get("phone"), b.get("email")]
    parties = Table([[_party("Sold by", s, seller_extra), _party("Bill / ship to", b, buyer_extra)]], colWidths=[91 * mm, 91 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [parties]
    if doc["taxed"]:
        story += [Spacer(1, 2 * mm), _p(f"Place of supply: {doc.get('place_of_supply') or '-'}  ·  Prices include GST", SMALL)]
    story.append(Spacer(1, 4 * mm))

    taxed, intra = doc["taxed"], doc["intra_state"]
    if taxed:
        head = ["Item", "HSN", "Qty", "Taxable", "GST %", *(["CGST", "SGST"] if intra else ["IGST"]), "Total"]
        widths = [62, 16, 10, 24, 13, *([20, 20] if intra else [40]), 22]
    else:
        head = ["Item", "Qty", "Unit price", "Total"]
        widths = [112, 14, 28, 28]
    rows = [head]
    for line in doc["lines"]:
        if taxed:
            tax_cells = [rs(line["cgst"]), rs(line["sgst"])] if intra else [rs(line["igst"])]
            rows.append([_p(line["description"]), line["hsn"], line["quantity"], rs(line["taxable"]), f"{line['rate']:g}%", *tax_cells, rs(line["total"])])
        else:
            rows.append([_p(line["description"]), line["quantity"], rs(line["unit_price"]), rs(line["total"])])
    tot = doc["totals"]
    if taxed:
        tax_totals = [rs(tot["cgst"]), rs(tot["sgst"])] if intra else [rs(tot["igst"])]
        rows.append(["Total", "", "", rs(tot["taxable"]), "", *tax_totals, rs(tot["total"])])
    else:
        rows.append(["Total", "", "", rs(tot["total"])])
    table = Table(rows, colWidths=[w * mm for w in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), MAROON),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, LINE),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, MAROON),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [table, Spacer(1, 3 * mm)]

    notes = [f"<b>Amount in words:</b> {escape(doc['amount_in_words'])}"]
    if doc.get("discount"):
        notes.append(f"Includes coupon {escape(doc['discount']['code'] or '')} discount of {rs(doc['discount']['amount'])}, shared across items by value.")
    if doc.get("reason"):
        notes.append(f"Reason: {escape(doc['reason'])}")
    pay = doc["payment"]
    if doc["kind"] == "credit_note":
        notes.append(f"Refunded {rs(pay['refunded'])} to the original payment method" + (f" (ref. {escape(pay['reference'])})" if pay.get("reference") else "") + ".")
    elif pay["method"] == "cod":
        notes.append("Payment: Cash on Delivery" + (" - collected." if pay["status"] == "cod_collected" else " - to be paid at delivery."))
    else:
        notes.append(f"Paid online: {rs(pay['paid'])}" + (f" (ref. {escape(pay['reference'])})" if pay.get("reference") else "")
                     + (f". Refunded: {rs(pay['refunded'])}" if pay.get("refunded") else "") + ".")
    if not taxed and doc["kind"] != "receipt":
        notes.append("GST details are not shown because the seller's GST registration or product tax rates are not set.")
    notes.append("This is a computer-generated document and does not require a signature.")
    for note in notes:
        story.append(Paragraph(note, SMALL))

    pdf.build(story)
    return buf.getvalue()
