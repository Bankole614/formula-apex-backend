from typing import List
from fastapi import APIRouter, WebSocket, HTTPException, Depends

from ..schemas.multiplayer import CreateRoomRequest, RoomSummary, RoomStateResponse
from ..services.room_manager import room_manager
from ..core.rate_limit import rate_limit_lobby

router = APIRouter(prefix="/api/multiplayer", tags=["Multiplayer"])


@router.get("/rooms", response_model=List[RoomSummary])
async def list_rooms():
    """List active public rooms that are accepting players."""
    return room_manager.list_public_rooms()


@router.post("/rooms", dependencies=[Depends(rate_limit_lobby)])
async def create_room(req: CreateRoomRequest):
    """Create a new multiplayer racing room."""
    room = room_manager.create_room(
        room_name=req.room_name,
        track_id=req.track_id,
        laps=req.laps,
        weather=req.weather,
        collision=req.collision,
        max_players=req.max_players,
        is_public=req.is_public,
    )
    return {"success": True, "roomId": room.room_id, "summary": room.get_summary().model_dump()}


@router.get("/rooms/{room_id}")
async def get_room(room_id: str):
    """Get the full snapshot state for a specific room."""
    room = room_manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.to_state_dict()


@router.websocket("/ws/{room_id}")
async def multiplayer_ws(websocket: WebSocket, room_id: str):
    """Live racing, telemetry broadcast, and lobby coordination WebSocket endpoint."""
    await room_manager.handle_websocket_session(websocket, room_id)
