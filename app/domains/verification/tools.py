"""Pure business logic functions for the verification domain.

- create_verification_request: starts the verification workflow for a source.
- schedule_visit: schedules on-site or remote inspection visit.
- record_checklist_result: records veterinary evaluation criteria results.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sources.models import Source
from app.domains.verification.models import ChecklistResult, VerificationRequest, Visit


async def create_verification_request(
    db: AsyncSession, source_id: int, evidence: str | None = None
) -> VerificationRequest:
    """Initiate the verification process for a shelter or rescue source."""
    req = VerificationRequest(source_id=source_id, submitted_evidence=evidence)
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def schedule_visit(
    db: AsyncSession,
    request_id: int,
    visit_type: str,
    scheduled_at: datetime,
    visitor_name: str,
) -> Visit:
    """Schedule an inspection visit and transition verification request status to scheduled."""
    result = await db.execute(
        select(VerificationRequest).where(VerificationRequest.id == request_id)
    )
    req = result.scalar_one_or_none()

    if req:
        req.status = "scheduled"

    visit = Visit(
        verification_request_id=request_id,
        visit_type=visit_type,
        scheduled_at=scheduled_at,
        visitor_name=visitor_name,
    )
    db.add(visit)
    await db.commit()
    await db.refresh(visit)
    return visit


async def record_checklist_result(
    db: AsyncSession, visit_id: int, checklist_data: list[dict[str, Any]]
) -> bool:
    """Save inspection results.

    If all criteria pass, source transitions to 'verified'. Otherwise, marked as rejected.
    """
    visit_res = await db.execute(select(Visit).where(Visit.id == visit_id))
    visit = visit_res.scalar_one_or_none()
    if not visit:
        return False

    all_passed = True

    for item in checklist_data:
        chk = ChecklistResult(
            visit_id=visit.id,
            criterion=item["criterion"],
            passed=item["passed"],
            notes=item.get("notes"),
        )
        db.add(chk)
        if not item["passed"]:
            all_passed = False

    visit.completed_at = datetime.now(UTC).replace(tzinfo=None)

    # Update verification request
    req_res = await db.execute(
        select(VerificationRequest).where(
            VerificationRequest.id == visit.verification_request_id
        )
    )
    req = req_res.scalar_one_or_none()

    if req:
        req.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
        req.status = "done" if all_passed else "rejected"

        # Update the Source entity
        source_res = await db.execute(select(Source).where(Source.id == req.source_id))
        source = source_res.scalar_one_or_none()

        if source:
            if all_passed:
                source.status = "verified"
                source.verified_at = datetime.now(UTC).replace(tzinfo=None)

    await db.commit()
    return all_passed
