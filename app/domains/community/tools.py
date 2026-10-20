"""Pure business logic functions for the community domain.

- register_update: records a new community update report.
- add_vote / cast_vote: registers community vote and updates consensus status when reaching threshold.
- get_entity_updates: retrieves existing updates for a campaign or animal ordered by vote count.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings

from app.domains.community.models import CommunityUpdate
from app.domains.animals.models import AnimalProfile
from app.domains.sterilization.models import Campaign


async def register_update(
    db: AsyncSession,
    update_type: str,
    note: str | None = None,
    campaign_id: int | None = None,
    animal_id: int | None = None,
) -> CommunityUpdate:
    """Register a new community report."""

    if campaign_id is not None:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        if not result.scalar_one_or_none():
            raise ValueError(f"Campaign with id {campaign_id} does not exist")

    if animal_id is not None:
        result = await db.execute(
            select(AnimalProfile).where(AnimalProfile.id == animal_id)
        )
        if not result.scalar_one_or_none():
            raise ValueError(f"Animal with id {animal_id} does not exist")

    new_update = CommunityUpdate(
        campaign_id=campaign_id,
        animal_id=animal_id,
        update_type=update_type,
        note=note,
        votes=1,  # Report creator automatically contributes initial seed vote
    )

    db.add(new_update)
    await db.commit()
    await db.refresh(new_update)
    return new_update


async def add_vote(db: AsyncSession, update_id: int) -> int | None:
    """Increment vote count on an existing update and return total votes."""
    result = await db.execute(
        select(CommunityUpdate).where(CommunityUpdate.id == update_id)
    )
    update_obj = result.scalar_one_or_none()

    if update_obj:
        update_obj.votes += 1
        await db.commit()
        return update_obj.votes
    return None


async def get_entity_updates(
    db: AsyncSession, campaign_id: int | None = None, animal_id: int | None = None
) -> list[CommunityUpdate]:
    """Retrieve community updates ordered by vote count and creation timestamp."""
    query = select(CommunityUpdate)

    if campaign_id:
        query = query.where(CommunityUpdate.campaign_id == campaign_id)
    elif animal_id:
        query = query.where(CommunityUpdate.animal_id == animal_id)

    query = query.order_by(
        CommunityUpdate.votes.desc(), CommunityUpdate.created_at.desc()
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def cast_vote(db: AsyncSession, update_id: int) -> CommunityUpdate | None:
    """Cast a vote. If consensus threshold is met, update official entity status."""
    result = await db.execute(
        select(CommunityUpdate).where(CommunityUpdate.id == update_id)
    )
    update_obj = result.scalar_one_or_none()

    if not update_obj:
        return None

    update_obj.votes += 1

    # --- Conflict resolution mechanism ---
    if update_obj.votes >= settings.COMMUNITY_VOTE_THRESHOLD:
        if update_obj.campaign_id:
            res_camp = await db.execute(
                select(Campaign).where(Campaign.id == update_obj.campaign_id)
            )
            camp = res_camp.scalar_one_or_none()
            if camp:
                if update_obj.update_type in ["full", "cancelled"]:
                    if camp.status != update_obj.update_type:
                        camp.status = update_obj.update_type
                elif update_obj.update_type == "confirmed":
                    camp.last_confirmed_at = datetime.now(timezone.utc)

        # --- Status resolution for animal profiles ---
        if update_obj.animal_id and update_obj.update_type in (
            "adopted",
            "in_treatment",
        ):
            res_animal = await db.execute(
                select(AnimalProfile).where(AnimalProfile.id == update_obj.animal_id)
            )
            animal = res_animal.scalar_one_or_none()
            if animal and animal.status != update_obj.update_type:
                animal.status = update_obj.update_type
                if update_obj.update_type == "adopted":
                    animal.adopted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(update_obj)
    return update_obj
