"""About Me / Verification / Account Info fields, DPDP consent, orders-missed
groundwork

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # About Me
    op.add_column("artist_profiles", sa.Column("profile_photo_url", sa.String(500), nullable=True))
    op.add_column("artist_profiles", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("artist_profiles", sa.Column("guardian_name", sa.String(120), nullable=True))
    op.add_column("artist_profiles", sa.Column("emergency_contact_name", sa.String(120), nullable=True))
    op.add_column("artist_profiles", sa.Column("emergency_contact_phone", sa.String(15), nullable=True))

    # Verification - id_proof_* generalizes and replaces the old
    # aadhaar-only fields and the generic kyc_doc_url; address_proof_doc_url
    # is new.
    op.add_column("artist_profiles", sa.Column("id_proof_type", sa.String(20), nullable=True))
    op.add_column("artist_profiles", sa.Column("id_proof_number", sa.String(30), nullable=True))
    op.add_column("artist_profiles", sa.Column("id_proof_doc_url", sa.String(500), nullable=True))
    op.add_column("artist_profiles", sa.Column("address_proof_doc_url", sa.String(500), nullable=True))

    op.execute(
        "UPDATE artist_profiles SET id_proof_type='aadhaar', id_proof_number=aadhaar_number, "
        "id_proof_doc_url=COALESCE(aadhaar_doc_url, kyc_doc_url) "
        "WHERE aadhaar_number IS NOT NULL OR aadhaar_doc_url IS NOT NULL OR kyc_doc_url IS NOT NULL"
    )

    op.drop_column("artist_profiles", "kyc_doc_url")
    op.drop_column("artist_profiles", "aadhaar_number")
    op.drop_column("artist_profiles", "aadhaar_doc_url")

    # Account info
    op.add_column("artist_profiles", sa.Column("bank_account_number", sa.String(30), nullable=True))
    op.add_column("artist_profiles", sa.Column("bank_ifsc_code", sa.String(11), nullable=True))
    op.add_column("artist_profiles", sa.Column("bank_account_holder_name", sa.String(120), nullable=True))

    # DPDP consent
    op.add_column("artist_profiles", sa.Column("consent_given", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("artist_profiles", sa.Column("consent_given_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("artist_profiles", "consent_given_at")
    op.drop_column("artist_profiles", "consent_given")
    op.drop_column("artist_profiles", "bank_account_holder_name")
    op.drop_column("artist_profiles", "bank_ifsc_code")
    op.drop_column("artist_profiles", "bank_account_number")

    op.add_column("artist_profiles", sa.Column("kyc_doc_url", sa.String(500), nullable=True))
    op.add_column("artist_profiles", sa.Column("aadhaar_number", sa.String(20), nullable=True))
    op.add_column("artist_profiles", sa.Column("aadhaar_doc_url", sa.String(500), nullable=True))

    op.drop_column("artist_profiles", "address_proof_doc_url")
    op.drop_column("artist_profiles", "id_proof_doc_url")
    op.drop_column("artist_profiles", "id_proof_number")
    op.drop_column("artist_profiles", "id_proof_type")

    op.drop_column("artist_profiles", "emergency_contact_phone")
    op.drop_column("artist_profiles", "emergency_contact_name")
    op.drop_column("artist_profiles", "guardian_name")
    op.drop_column("artist_profiles", "date_of_birth")
    op.drop_column("artist_profiles", "profile_photo_url")
