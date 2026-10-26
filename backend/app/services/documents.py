"""Order documents: payment receipt, GST tax invoice and GST credit note -
built once here as plain data, then shown on the website, rendered to PDF
and attached to emails, so all three always agree.

GST treatment (prices are MRPs including GST):
- each line's tax is worked backwards from its price after its share of
  any coupon discount (shared by value);
- delivery and COD charges are taxed at the order's highest item rate
  (mixed supply);
- same state as the seller -> CGST + SGST, otherwise IGST;
- a tax invoice needs the seller GSTIN + state and a rate on every item,
  otherwise the document is a plain receipt;
- a credit note reverses the invoice in proportion to the amount refunded.
Have an accountant confirm HSN codes, rates and this treatment.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.payment_ops import Refund
from app.models.shop import ShopOrder, ShopOrderItem

settings = get_settings()
IST = timedelta(hours=5, minutes=30)


def r2(value: float) -> float:
    return round(value + 1e-9, 2)


def seller() -> dict:
    return {
        "name": settings.business_legal_name or "AryaVeda Mehndi",
        "address": settings.business_address,
        "state": settings.business_state,
        "gstin": settings.business_gstin,
        "email": settings.support_email,
        "phone": settings.support_phone,
    }


def _ist_date(value: datetime | None) -> str | None:
    return (value + IST).strftime("%d %b %Y") if value else None


def _split(inclusive: float, rate: float, intra: bool) -> dict:
    taxable = r2(inclusive / (1 + rate / 100))
    tax = r2(inclusive - taxable)
    if intra:
        cgst = r2(tax / 2)
        return {"taxable": taxable, "cgst": cgst, "sgst": r2(tax - cgst), "igst": 0.0}
    return {"taxable": taxable, "cgst": 0.0, "sgst": 0.0, "igst": tax}


def _items(db: Session, order: ShopOrder) -> list[ShopOrderItem]:
    return db.query(ShopOrderItem).filter(ShopOrderItem.order_id == order.id).order_by(ShopOrderItem.product_name).all()


def can_tax_invoice(order_items: list[ShopOrderItem]) -> bool:
    s = seller()
    return bool(s["gstin"] and s["state"] and order_items and all(i.gst_rate is not None for i in order_items))


def _lines(order: ShopOrder, items: list[ShopOrderItem], taxed: bool) -> tuple[list[dict], bool]:
    """Invoice lines (items, then charges) with each line's inclusive total."""
    intra = bool(order.shipping_state) and order.shipping_state.strip().lower() == (settings.business_state or "").strip().lower()
    items_amount = order.items_amount if order.items_amount is not None else sum(i.subtotal for i in items)
    lines = []
    for i in items:
        share = (order.discount_amount or 0) * i.subtotal / items_amount if items_amount else 0
        total = r2(i.subtotal - share)
        line = {
            "description": f"{i.product_name}{f' ({i.variant_label})' if i.variant_label else ''}",
            "hsn": i.hsn_code or "",
            "quantity": i.quantity,
            "unit_price": i.unit_price,
            "rate": i.gst_rate,
            "total": total,
        }
        if taxed:
            line.update(_split(total, i.gst_rate, intra))
        lines.append(line)
    top_rate = max((i.gst_rate for i in items if i.gst_rate is not None), default=0)
    for label, amount in (("Delivery charges", order.shipping_fee), ("Cash on Delivery charges", order.cod_fee)):
        if amount and amount > 0:
            line = {"description": label, "hsn": "", "quantity": 1, "unit_price": amount, "rate": top_rate if taxed else None, "total": r2(amount)}
            if taxed:
                line.update(_split(amount, top_rate, intra))
            lines.append(line)
    return lines, intra


def _totals(lines: list[dict], taxed: bool) -> dict:
    keys = ("taxable", "cgst", "sgst", "igst", "total") if taxed else ("total",)
    return {k: r2(sum(line[k] for line in lines)) for k in keys}


def _buyer(order: ShopOrder) -> dict:
    return {
        "name": order.shipping_name,
        "phone": order.shipping_phone,
        "email": order.contact_email,
        "address": order.shipping_address,
        "state": order.shipping_state,
        "pincode": order.shipping_pincode,
    }


def order_document(db: Session, order: ShopOrder) -> dict:
    """Tax invoice once dispatched (and GST details are set up); before
    that, or without GST details, a receipt of what was ordered and paid."""
    items = _items(db, order)
    taxed = bool(order.invoice_number) and can_tax_invoice(items)
    lines, intra = _lines(order, items, taxed)
    if order.invoice_number:
        kind, title, number, date = ("tax_invoice" if taxed else "invoice"), ("Tax Invoice" if taxed else "Invoice"), order.invoice_number, order.invoiced_at
    else:
        kind, title, number, date = "receipt", "Order Receipt", f"Order {str(order.id)[:8].upper()}", order.confirmed_at or order.created_at
    return {
        "kind": kind,
        "title": title,
        "number": number,
        "date": _ist_date(date),
        "order_id": str(order.id),
        "seller": seller(),
        "buyer": _buyer(order),
        "place_of_supply": order.shipping_state,
        "taxed": taxed,
        "intra_state": intra,
        "lines": lines,
        "totals": _totals(lines, taxed),
        "discount": {"code": order.coupon_code, "amount": order.discount_amount} if order.discount_amount else None,
        "payment": {
            "method": order.payment_method,
            "status": order.payment_status,
            "paid": order.amount_paid,
            "refunded": order.amount_refunded,
            "reference": order.razorpay_payment_id,
        },
        "amount_in_words": rupees_in_words(order.total_amount),
    }


def credit_note_document(db: Session, refund: Refund, order: ShopOrder) -> dict:
    """GST credit note for a refund on an invoiced order: the invoice lines
    reversed in proportion to the amount refunded."""
    items = _items(db, order)
    taxed = can_tax_invoice(items)
    invoice_lines, intra = _lines(order, items, taxed)
    refunded = refund.amount_refunded or 0
    invoice_total = sum(line["total"] for line in invoice_lines) or 1
    factor = min(refunded / invoice_total, 1)
    lines = []
    for line in invoice_lines:
        total = r2(line["total"] * factor)
        new = {**line, "total": total}
        if taxed:
            new.update(_split(total, line["rate"], intra))
        lines.append(new)
    # Rounding: make the lines add up to exactly the amount refunded.
    if lines:
        drift = r2(refunded - sum(line["total"] for line in lines))
        if drift:
            lines[0]["total"] = r2(lines[0]["total"] + drift)
            if taxed:
                lines[0].update(_split(lines[0]["total"], lines[0]["rate"], intra))
    return {
        "kind": "credit_note",
        "title": "Credit Note",
        "number": refund.credit_note_number,
        "date": _ist_date(refund.processed_at),
        "order_id": str(order.id),
        "against": {"number": order.invoice_number, "date": _ist_date(order.invoiced_at)},
        "reason": refund.reason,
        "seller": seller(),
        "buyer": _buyer(order),
        "place_of_supply": order.shipping_state,
        "taxed": taxed,
        "intra_state": intra,
        "lines": lines,
        "totals": _totals(lines, taxed),
        "payment": {"method": "online", "status": "refunded", "refunded": refunded, "reference": refund.razorpay_refund_id},
        "amount_in_words": rupees_in_words(refunded),
    }


# ------------------------------------------------------------- in words --

_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _below_hundred(n: int) -> str:
    return _ONES[n] if n < 20 else f"{_TENS[n // 10]} {_ONES[n % 10]}".strip()


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = [f"{_ONES[hundreds]} Hundred"] if hundreds else []
    if rest:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def number_in_words(n: int) -> str:
    """Indian system: crore, lakh, thousand."""
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (10**3, "Thousand")):
        if n >= size:
            count, n = divmod(n, size)
            parts.append(f"{number_in_words(count) if count >= 100 else _below_hundred(count)} {name}")
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def rupees_in_words(amount: float) -> str:
    rupees, paise = divmod(int(round(amount * 100)), 100)
    text = f"Rupees {number_in_words(rupees)}"
    if paise:
        text += f" and {_below_hundred(paise)} Paise"
    return f"{text} Only"
