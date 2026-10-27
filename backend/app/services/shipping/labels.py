"""Shipping labels (4x6 in, one per page - the size thermal label printers
take) and the pickup manifest (A4), generated on request so customer
addresses are never stored as files. A courier that supplies its own label
(Shipment.label_url) should be printed from there instead."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.time import utcnow
from app.models.shipping import Shipment
from app.services.documents import IST, seller

LABEL = (4 * inch, 6 * inch)
BODY = ParagraphStyle("lbl", fontName="Helvetica", fontSize=9, leading=11)
BIG = ParagraphStyle("lblbig", fontName="Helvetica-Bold", fontSize=11, leading=13)


def _p(text: str, style=BODY) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def labels_pdf(rows: list[tuple[Shipment, dict, int]]) -> bytes:
    """rows: (shipment, party - see service.shipment_party, item count).
    A return pickup's label is addressed to us, from the customer."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LABEL)
    width, height = LABEL
    s = seller()
    for shipment, party, items in rows:
        m = 0.18 * inch
        # Header: courier and payment mode.
        c.setFont("Helvetica-Bold", 12)
        c.drawString(m, height - m - 10, (shipment.courier_name or "Courier")[:30])
        c.setFont("Helvetica-Bold", 14)
        mode = f"COD  Rs. {shipment.cod_amount:,.2f}" if shipment.cod_amount else "PREPAID"
        c.drawRightString(width - m, height - m - 10, mode)
        c.line(m, height - m - 18, width - m, height - m - 18)

        # Barcode of the AWB (or our order reference until there is one).
        code = shipment.awb or party["ref"]
        barcode = code128.Code128(code, barHeight=0.7 * inch, barWidth=1.1)
        bx = max((width - barcode.width) / 2, m)
        barcode.drawOn(c, bx, height - m - 0.95 * inch)
        c.setFont("Helvetica", 9)
        c.drawCentredString(width / 2, height - m - 1.08 * inch, ("AWB " if shipment.awb else "Ref ") + code)

        # Ship to (a return goes to us, from the customer).
        if shipment.direction == "reverse":
            to = ["<b>RETURN TO</b>", f"<b>{escape(s['name'])}</b>", escape(s.get("address") or "").replace("\n", "<br/>"),
                  escape(s.get("phone") or "")]
        else:
            to = ["<b>SHIP TO</b>", f"<b>{escape(party['name'])}</b>", escape(party['address'] or "").replace("\n", "<br/>")]
            if party.get("state") or party.get("pincode"):
                to.append(f"<b>{escape(' - '.join(x for x in (party.get('state'), party.get('pincode')) if x))}</b>")
            to.append(f"Ph: {escape(party['phone'] or '')}")
        Frame(m, 2.0 * inch, width - 2 * m, 2.6 * inch, showBoundary=0, leftPadding=0, rightPadding=0).addFromList(
            [Paragraph("<br/>".join(t for t in to if t), BIG)], c)

        # Parcel details.
        c.line(m, 2.0 * inch, width - m, 2.0 * inch)
        details = (f"Ref {party['ref']}  ·  {items} item(s)  ·  {shipment.weight_g / 1000:.2f} kg  ·  "
                   f"{shipment.length_cm:g}x{shipment.breadth_cm:g}x{shipment.height_cm:g} cm")
        Frame(m, 1.45 * inch, width - 2 * m, 0.55 * inch, showBoundary=0, leftPadding=0, rightPadding=0).addFromList([_p(details)], c)

        # Return address.
        c.line(m, 1.45 * inch, width - m, 1.45 * inch)
        if shipment.direction == "reverse":
            ret = "\n".join(x for x in (f"From (customer): {party['name']}", party["address"] or "", " - ".join(x for x in (party.get("state"), party.get("pincode")) if x),
                                        f"Ph: {party['phone']}") if x)
        else:
            ret = "\n".join(x for x in (f"If undelivered, return to: {s['name']}", s.get("address") or "", s.get("phone") or "",
                                        f"GSTIN {s['gstin']}" if s.get("gstin") else "") if x)
        Frame(m, m, width - 2 * m, 1.45 * inch - m, showBoundary=0, leftPadding=0, rightPadding=0).addFromList([_p(ret)], c)
        c.showPage()
    c.save()
    return buf.getvalue()


def manifest_pdf(rows: list[tuple[Shipment, dict, int]]) -> bytes:
    """Pickup manifest: one line per parcel, signed by the courier at pickup."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Pickup manifest")
    now = utcnow() + IST
    s = seller()
    head = [["#", "AWB / Ref", "Courier", "Order", "Consignee", "PIN", "Weight (kg)", "Mode", "COD (Rs.)"]]
    body = []
    total_cod = 0.0
    for n, (shipment, party, _items) in enumerate(rows, start=1):
        total_cod += shipment.cod_amount or 0
        body.append([n, shipment.awb or party["ref"], shipment.courier_name or "", party["ref"],
                     party["name"] + (" (return)" if shipment.direction == "reverse" else ""), party.get("pincode") or "", f"{shipment.weight_g / 1000:.2f}",
                     "COD" if shipment.cod_amount else "Prepaid", f"{shipment.cod_amount:,.2f}" if shipment.cod_amount else "-"])
    body.append(["", "", "", "", "", "", "", "Total", f"{total_cod:,.2f}"])
    table = Table(head + body, repeatRows=1, colWidths=[10 * mm, 42 * mm, 32 * mm, 24 * mm, 60 * mm, 18 * mm, 22 * mm, 18 * mm, 24 * mm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5C1A21")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -2), 0.25, colors.HexColor("#E1D2B8")),
        ("ALIGN", (6, 0), (-1, -1), "RIGHT"),
    ]))
    story = [
        Paragraph(f"<b>Pickup manifest</b> - {escape(s['name'])} - {now:%d %b %Y %H:%M} IST - {len(rows)} parcel(s)", BIG),
        Spacer(1, 4 * mm), table, Spacer(1, 12 * mm),
        Paragraph("Handed over by (name &amp; signature): ______________________________    "
                  "Received by courier (name, signature &amp; time): ______________________________", BODY),
    ]
    doc.build(story)
    return buf.getvalue()
