import hashlib
import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from backend.app.audit import record_audit_event
from backend.app.db import SessionLocal
from backend.app.decisioning import orchestrate_assessment
from backend.app.main import initialize_database
from backend.app.models import (
    Assessment,
    Counterparty,
    ScreeningEntry,
    ScreeningList,
    ScreeningListVersion,
    TradeTransaction,
    TransactionParty,
    User,
)
from backend.app.screening import normalize_name


DEMO_REFERENCE = "DEMO-EXPORT-001"


def seed() -> dict:
    initialize_database()
    with SessionLocal() as db:
        admin = db.scalar(select(User).order_by(User.created_at))
        if admin is None:
            raise RuntimeError("No administrator is available")

        source = db.scalar(select(ScreeningList).where(ScreeningList.code == "PUBLIC-DEMO"))
        if source is None:
            source = ScreeningList(
                code="PUBLIC-DEMO",
                name="Fictional Public Demo Screening List",
                authority="TradeGuard AI demonstration",
                source_url="https://example.test/tradeguard/public-demo",
            )
            db.add(source)
            db.flush()
            content = b"PUBLIC-SAFE FICTIONAL DEMONSTRATION DATA v1"
            version = ScreeningListVersion(
                screening_list_id=source.id,
                version="demo-v1",
                status="active",
                effective_at=datetime(2026, 10, 21),
                checksum_sha256=hashlib.sha256(content).hexdigest(),
                source_filename="fictional-public-demo.csv",
                source_file_key="public-demo-v1",
                entry_count=1,
                imported_by_id=admin.id,
            )
            db.add(version)
            db.flush()
            db.add(
                ScreeningEntry(
                    list_version_id=version.id,
                    source_entry_id="DEMO-LIST-001",
                    primary_name="Fictional Restricted Example Corp",
                    normalized_name=normalize_name("Fictional Restricted Example Corp"),
                    entity_type="entity",
                    country="ZZ",
                    program="FICTIONAL DEMO ONLY",
                    aliases_json="[]",
                    identifiers_json="{}",
                    remarks="Not a real entity or official list record.",
                )
            )
            source.active_version_id = version.id

        counterparty = db.scalar(
            select(Counterparty).where(
                Counterparty.jurisdiction == "GB",
                Counterparty.registration_number == "DEMO-REG-001",
            )
        )
        if counterparty is None:
            counterparty = Counterparty(
                legal_name="Northstar Demo Components Ltd",
                jurisdiction="GB",
                registration_number="DEMO-REG-001",
                status="active",
                website="https://example.test/northstar-demo",
                primary_address="1 Example Way, London, GB",
                notes="Fictional public-safe portfolio demonstration record.",
                created_by_id=admin.id,
            )
            db.add(counterparty)
            db.flush()

        transaction = db.scalar(
            select(TradeTransaction).where(TradeTransaction.reference == DEMO_REFERENCE)
        )
        if transaction is None:
            transaction = TradeTransaction(
                reference=DEMO_REFERENCE,
                product_description="Commercial refrigeration components",
                hs_code="8418.99",
                quantity=Decimal("100"),
                quantity_unit="units",
                origin_country="GB",
                destination_country="US",
                amount=Decimal("85000"),
                currency="USD",
                payment_method="letter_of_credit",
                payment_terms_days=15,
                deposit_percentage=Decimal("35"),
                incoterm="FOB",
                bank_beneficiary_name=counterparty.legal_name,
                bank_beneficiary_country="GB",
                requested_credit_exposure=Decimal("55250"),
                end_use="Installation in fictional commercial cold-storage facilities",
                created_by_id=admin.id,
            )
            transaction.parties = [
                TransactionParty(
                    role="seller",
                    name=counterparty.legal_name,
                    country="GB",
                    registration_number=counterparty.registration_number,
                    counterparty_id=counterparty.id,
                ),
                TransactionParty(
                    role="end_user",
                    name="Public Safe Demonstration Customer",
                    country="US",
                ),
            ]
            db.add(transaction)
            db.flush()

        assessment = db.scalar(
            select(Assessment).where(Assessment.transaction_id == transaction.id)
        )
        if assessment is None:
            assessment = orchestrate_assessment(db, transaction, admin)
            record_audit_event(
                db,
                actor_id=admin.id,
                action="demo.seeded",
                object_type="assessment",
                object_id=assessment.id,
                details={"public_safe": True, "reference": DEMO_REFERENCE},
            )
        db.commit()
        return {
            "counterparty_id": counterparty.id,
            "transaction_id": transaction.id,
            "assessment_id": assessment.id,
            "recommendation": assessment.recommendation,
        }


if __name__ == "__main__":
    print(json.dumps(seed(), indent=2))
