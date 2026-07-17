"""Tenant-scoped publication locator validation and conflict translation."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Publication


def assert_publication_locator_available(
    db: Session,
    *,
    organization_id: str,
    platform: str,
    external_url: str,
    external_content_id: str,
) -> None:
    """Reject a locator already registered on the same tenant and platform.

    Database partial unique indexes provide the final concurrency guarantee;
    this preflight check gives callers a stable, actionable API response.
    """

    filters = (
        Publication.organization_id == organization_id,
        Publication.platform == platform,
    )
    if external_content_id and db.scalar(
        select(Publication.id).where(
            *filters,
            Publication.external_content_id == external_content_id,
        )
    ):
        raise locator_conflict("external_content_id")
    if external_url and db.scalar(
        select(Publication.id).where(
            *filters,
            Publication.external_url == external_url,
        )
    ):
        raise locator_conflict("external_url")


def locator_conflict(locator: str | None = None) -> HTTPException:
    if locator == "external_content_id":
        detail = "This platform content ID is already linked to a publication"
    elif locator == "external_url":
        detail = "This platform URL is already linked to a publication"
    else:
        detail = "This platform publication locator is already linked to a publication"
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
