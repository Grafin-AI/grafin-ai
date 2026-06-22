import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from garda_ai_backend.api.deps import RedisDep, SettingsDep
from garda_ai_backend.api.ws_auth import authenticate_ws_token
from garda_ai_backend.realtime.channels import LIVE_EVENTS_CHANNEL

router = APIRouter(tags=["ws"])

_QUEUE_MAX = 100
_RESYNC = json.dumps({"type": "resync"})


@router.websocket("/api/v1/ws/live")
async def ws_live(websocket: WebSocket, redis: RedisDep, settings: SettingsDep) -> None:
    user = authenticate_ws_token(
        websocket.query_params.get("token", ""), settings.jwt_secret
    )
    if user is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(LIVE_EVENTS_CHANNEL)
    await websocket.send_json({"type": "connected"})

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAX)

    async def reader() -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                if queue.full():
                    while not queue.empty():
                        queue.get_nowait()
                    await queue.put(_RESYNC)
                await queue.put(message["data"])
        except asyncio.CancelledError:
            raise

    async def writer() -> None:
        try:
            while True:
                await websocket.send_text(await queue.get())
        except asyncio.CancelledError:
            raise

    reader_task = asyncio.create_task(reader())
    writer_task = asyncio.create_task(writer())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        writer_task.cancel()
        await asyncio.gather(reader_task, writer_task, return_exceptions=True)
        await pubsub.unsubscribe(LIVE_EVENTS_CHANNEL)
        await pubsub.aclose()
