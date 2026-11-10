"""Shopping locations, visit detection and location preferences."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models import User
from app.models.enums import VisitStatus
from app.schemas.location import (
    LocationSettingsOut,
    LocationSettingsPatch,
    TrackedLocationCreate,
    TrackedLocationOut,
    TrackedLocationUpdate,
    VisitDetectRequest,
    VisitOut,
    VisitUpdate,
)
from app.security.deps import get_current_user
from app.services import visits as visit_service

router = APIRouter(prefix="/shopping", tags=["shopping"])


# -------------------------------------------------------------------- settings
@router.get("/location-settings", response_model=LocationSettingsOut)
def get_location_settings(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> LocationSettingsOut:
    return LocationSettingsOut(**visit_service.location_settings(db, user))


@router.patch("/location-settings", response_model=LocationSettingsOut)
def patch_location_settings(
    payload: LocationSettingsPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LocationSettingsOut:
    return LocationSettingsOut(**visit_service.update_location_settings(db, user, payload))


# ------------------------------------------------------------------- locations
@router.get("/locations", response_model=list[TrackedLocationOut])
def get_locations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[TrackedLocationOut]:
    return [TrackedLocationOut(**row) for row in visit_service.list_locations(db, user)]


@router.post("/locations", response_model=TrackedLocationOut, status_code=201)
def post_location(
    payload: TrackedLocationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrackedLocationOut:
    row = visit_service.create_location(db, user, payload)
    created = next(item for item in visit_service.list_locations(db, user) if item["id"] == row.id)
    return TrackedLocationOut(**created)


# Declared before ``/{location_id}`` so the literal path is not swallowed by the
# UUID converter.
@router.post("/locations/from-visit/{visit_id}", response_model=TrackedLocationOut, status_code=201)
def post_location_from_visit(
    visit_id: uuid.UUID,
    payload: TrackedLocationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrackedLocationOut:
    row = visit_service.add_tracked_from_visit(db, user, visit_id, payload)
    created = next(item for item in visit_service.list_locations(db, user) if item["id"] == row.id)
    return TrackedLocationOut(**created)


@router.post("/locations/{location_id}/arrive")
def post_arrival(
    location_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Called by the Android geofence receiver: an identifier, never a coordinate."""
    return visit_service.record_arrival(db, user, location_id)


@router.patch("/locations/{location_id}", response_model=TrackedLocationOut)
def patch_location(
    location_id: uuid.UUID,
    payload: TrackedLocationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrackedLocationOut:
    row = visit_service.update_location(db, user, location_id, payload)
    updated = next(item for item in visit_service.list_locations(db, user) if item["id"] == row.id)
    return TrackedLocationOut(**updated)


@router.delete("/locations/{location_id}", status_code=204)
def remove_location(
    location_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    visit_service.delete_location(db, user.id, location_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------- visits
@router.get("/visits")
def get_visits(
    days: int = Query(default=90, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return visit_service.list_visits(db, user, days=days)


@router.post("/visits/detect")
def post_detect(
    payload: VisitDetectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return visit_service.detect_visit(db, user, payload)


@router.patch("/visits/{visit_id}", response_model=VisitOut)
def patch_visit(
    visit_id: uuid.UUID,
    payload: VisitUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisitOut:
    visit = visit_service.set_visit_status(db, user, visit_id, payload.status)
    row = next(
        item
        for item in visit_service.list_visits(db, user, days=365)["items"]
        if item["id"] == visit.id
    )
    return VisitOut(**row)


@router.post("/visits/{visit_id}/ignore", response_model=VisitOut)
def ignore_visit(
    visit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VisitOut:
    visit = visit_service.set_visit_status(db, user, visit_id, VisitStatus.IGNORED)
    row = next(
        item
        for item in visit_service.list_visits(db, user, days=365)["items"]
        if item["id"] == visit.id
    )
    return VisitOut(**row)


@router.delete("/visits/{visit_id}", status_code=204)
def remove_visit(
    visit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    visit_service.delete_visit(db, user.id, visit_id)
    return Response(status_code=204)


@router.delete("/visits", status_code=200)
def clear_visits(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Delete every visit for this user. Tracked locations are kept."""
    return {"deleted": visit_service.clear_history(db, user.id)}


@router.get("/store-spending")
def get_store_spending(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return visit_service.spending_by_store(db, user)
