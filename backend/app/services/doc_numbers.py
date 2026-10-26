"""Consecutive document numbers per Indian financial year (April-March, in
IST), as GST requires for invoices and credit notes:

    invoice      AV2627-000001
    credit note  CN2627-000001

The counter row is locked while a number is taken, so two documents issued
at the same moment can't share a number. Numbers are only taken inside the
transaction that issues the document, so a rollback leaves no gap behind
except in the rare case of a failure after commit.
"""

from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.shop import ShopInvoiceCounter

IST = timedelta(hours=5, minutes=30)
# kind -> (counter series prefix, printed prefix)
SERIES = {"invoice": ("INV", "AV"), "credit_note": ("CN", "CN")}


def financial_year(now=None) -> str:
    now = (now or utcnow()) + IST
    start = now.year if now.month >= 4 else now.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def next_document_number(db: Session, kind: str) -> str:
    series_prefix, printed = SERIES[kind]
    fy = financial_year()
    series = f"{series_prefix}{fy}"
    db.execute(pg_insert(ShopInvoiceCounter).values(series=series, last_number=0).on_conflict_do_nothing())
    counter = db.query(ShopInvoiceCounter).filter(ShopInvoiceCounter.series == series).with_for_update().one()
    counter.last_number += 1
    return f"{printed}{fy}-{counter.last_number:06d}"
