from fastapi import APIRouter, HTTPException, status

from garda_ai_backend.api.deps import CurrentUserDep, SessionDep
from garda_ai_backend.api.view_schemas import AlertItem, AlertsResponse
from garda_ai_backend.repositories.alerts import AlertsRepository

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _item(a) -> AlertItem:
    return AlertItem(
        id=a.id, event_seq=a.event_seq, severity=a.severity, typology=a.typology,
        created_at=a.created_at.isoformat(), acknowledged=a.acknowledged_at is not None,
    )


@router.get("", response_model=AlertsResponse)
async def list_alerts(session: SessionDep, _: CurrentUserDep, status: str = "all") -> AlertsResponse:
    rows = await AlertsRepository(session).list_alerts(active_only=(status == "active"))
    return AlertsResponse(alerts=[_item(a) for a in rows])


@router.post("/{alert_id}/ack", response_model=AlertItem)
async def ack(alert_id: int, session: SessionDep, user: CurrentUserDep) -> AlertItem:
    alert = await AlertsRepository(session).acknowledge(alert_id, user.id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    await session.commit()
    return _item(alert)
