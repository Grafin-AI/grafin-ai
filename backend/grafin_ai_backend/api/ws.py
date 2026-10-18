from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from grafin_ai_backend.api.deps import RedisDep, SettingsDep
from grafin_ai_backend.api.ws_auth import authenticate_ws_token
from grafin_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL

router = APIRouter(tags=["ws"])

# Idle poll timeout. Events stream continuously, so a forward (and thus client-
# disconnect detection via send) happens well within this; on a quiet channel the
# loop simply re-polls.
_POLL_TIMEOUT = 15.0


@router.websocket("/api/v1/ws/live")
async def ws_live(websocket: WebSocket, redis: RedisDep, settings: SettingsDep) -> None:
    user = authenticate_ws_token(
        websocket.query_params.get("token", ""), settings.jwt_secret
    )
    if user is None:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(LIVE_EVENTS_CHANNEL)
    await websocket.send_json({"type": "connected"})

    # Single-loop relay: read one message at a time and forward it. We deliberately
    # do NOT run a concurrent reader task + a separate `receive_text()` detector:
    # that send-from-a-task while the main coroutine awaits receive works under
    # Starlette's in-process test transport but does NOT deliver under uvicorn's
    # real WebSocket transport. Here `send_text` raises WebSocketDisconnect when the
    # client goes away, which ends the loop. The published string is already the full
    # event JSON the dashboard expects; clients still backfill gaps via
    # GET /transactions/live?after_seq= (the consistency contract).
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_POLL_TIMEOUT
            )
            if message is not None and message.get("type") == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        # Best-effort cleanup: the connection may already be broken at this point.
        try:
            await pubsub.unsubscribe(LIVE_EVENTS_CHANNEL)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001 - cleanup must not raise on a dead socket
            pass
