"""Transactional email for shop orders, sent by the worker with retries:
order confirmed (receipt attached), shipped (GST invoice attached) and
refund processed (credit note attached). Off until SMTP_HOST is set, and
skipped for orders without a contact email - the jobs then just finish.
"""

import logging
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from html import escape

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.payment_ops import Refund
from app.models.shop import ShopOrder
from app.services import pdf
from app.services.documents import credit_note_document, order_document
from app.services.jobs import job_handler

log = logging.getLogger(__name__)
settings = get_settings()


def email_enabled() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(to: str, subject: str, text: str, html: str, attachments: list[tuple[str, bytes]] = ()) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    if settings.support_email:
        msg["Reply-To"] = settings.support_email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for filename, data in attachments:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    context = ssl.create_default_context()
    if settings.smtp_port == 465:  # implicit TLS ("SSL") rather than STARTTLS
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=context)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    with server as smtp:
        if settings.smtp_port != 465 and settings.smtp_starttls:
            smtp.starttls(context=context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def _layout(heading: str, paragraphs: list[str], order: ShopOrder) -> tuple[str, str]:
    link = f"{settings.public_site_url.rstrip('/')}/shop/orders/{order.id}"
    text = "\n\n".join([heading, *paragraphs, f"View your order: {link}", "- AryaVeda Mehndi"])
    body = "".join(f"<p style='margin:0 0 12px'>{escape(p)}</p>" for p in paragraphs)
    html = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#2B1712">
<div style="background:#5C1A21;color:#FBF6EC;padding:16px 20px;font-size:18px;font-weight:bold">AryaVeda Mehndi</div>
<div style="padding:20px;background:#FBF6EC;border:1px solid #E1D2B8">
<h2 style="margin:0 0 12px;color:#5C1A21;font-size:18px">{escape(heading)}</h2>{body}
<p style="margin:16px 0 0"><a href="{escape(link)}" style="background:#5C1A21;color:#FBF6EC;padding:10px 16px;text-decoration:none;border-radius:6px">View your order</a></p>
</div>
<p style="font-size:11px;color:#5A453D;padding:8px 20px">{escape(settings.business_legal_name or 'AryaVeda Mehndi')}{(' · ' + escape(settings.support_email)) if settings.support_email else ''}</p>
</div>"""
    return text, html


def _order_or_skip(db: Session, order_id: str) -> ShopOrder | None:
    order = db.get(ShopOrder, uuid.UUID(order_id))
    if order is None or not order.contact_email or not email_enabled():
        return None
    return order


@job_handler("email.shop_order_confirmed")
def order_confirmed(db: Session, payload: dict) -> str:
    order = _order_or_skip(db, payload["order_id"])
    if order is None:
        return "skipped"
    doc = order_document(db, order)
    paid = (f"Payment of ₹{order.amount_paid:g} received." if order.payment_method == "online"
            else f"Please keep ₹{order.total_amount:g} ready - you'll pay at delivery.")
    text, html = _layout("Your order is confirmed", [f"Hi {order.shipping_name}, thank you for your order.", paid,
                                                     "We'll email you the invoice and tracking details as soon as it ships."], order)
    send_email(order.contact_email, "Order confirmed - AryaVeda Mehndi", text, html, [(f"receipt-{str(order.id)[:8]}.pdf", pdf.render(doc))])
    return "sent"


@job_handler("email.shop_order_shipped")
def order_shipped(db: Session, payload: dict) -> str:
    order = _order_or_skip(db, payload["order_id"])
    if order is None:
        return "skipped"
    doc = order_document(db, order)
    tracking = (f"Courier: {order.courier_name or 'our courier'}, tracking no. {order.tracking_number}."
                if order.tracking_number else "Tracking details will appear on your order page.")
    lines = [f"Hi {order.shipping_name}, your order is on its way.", tracking]
    if order.tracking_url:
        lines.append(f"Track it here: {order.tracking_url}")
    lines.append(f"Your invoice {order.invoice_number} is attached.")
    text, html = _layout("Your order has shipped", lines, order)
    send_email(order.contact_email, f"Shipped: invoice {order.invoice_number} - AryaVeda Mehndi", text, html, [(f"{order.invoice_number}.pdf", pdf.render(doc))])
    return "sent"


@job_handler("email.shop_refund")
def refund_processed(db: Session, payload: dict) -> str:
    refund = db.get(Refund, uuid.UUID(payload["refund_id"]))
    if refund is None or refund.target_type != "shop_order":
        return "skipped"
    order = _order_or_skip(db, str(refund.target_id))
    if order is None:
        return "skipped"
    attachments = []
    lines = [f"Hi {order.shipping_name}, we've refunded ₹{(refund.amount_refunded or 0):g} to your original payment method.",
             "Banks usually show it within 5-7 working days."]
    if refund.credit_note_number:
        attachments.append((f"{refund.credit_note_number}.pdf", pdf.render(credit_note_document(db, refund, order))))
        lines.append(f"Credit note {refund.credit_note_number} is attached for your records.")
    text, html = _layout("Your refund is on its way", lines, order)
    send_email(order.contact_email, "Refund processed - AryaVeda Mehndi", text, html, attachments)
    return "sent"
