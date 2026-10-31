import asyncio
import json
import logging
import random
import string
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("multiplayer")

router = APIRouter(prefix="/api/multiplayer", tags=["Multiplayer"])

# ----------------- Models -----------------
class CreateRoomRequest(BaseModel):
    room_name: str = Field(default="Apex Grand Prix", max_length=40)
    track_id: str = Field(default="default")
    laps: int = Field(default=5, ge=1, le=30)
    weather: str = Field(default="dry")
    collision: str = Field(default="normal")
    max_players: int = Field(default=8, ge=2, le=16)
    is_public: bool = Field(default=True)
    host_name: str = Field(default="Host Driver", max_length=24)
    car_model: str = Field(default="low_poly_f1")
    car_color: str = Field(default="#e10600")

class RoomSummary(BaseModel):
    room_id: str
    room_name: str
    track_id: str
    laps: int
    weather: str
    collision: str
    player_count: int
    spectator_count: int
    max_players: int
    status: str
    host_name: str
    created_at: float

# ----------------- Player & Room Representation -----------------
class ConnectedPlayer:
    def __init__(
        self,
        player_id: str,
        name: str,
        team_id: str,
        car_model: str,
        car_color: str,
        driver_id: str,
        is_spectator: bool = False,
        is_host: bool = False,
        ws: Optional[WebSocket] = None,
    ):
        self.player_id = player_id
        self.name = name
        self.team_id = team_id
        self.car_model = car_model
        self.car_color = car_color
        self.driver_id = driver_id
        self.is_spectator = is_spectator
        self.is_host = is_host
        self.ready = is_host  # Host is ready by default
        self.ws: Optional[WebSocket] = ws
        self.slot = -1
        self.last_seen = time.time()
        self.telemetry: dict = {}
        self.finished = False
        self.finish_time_ticks: Optional[int] = None
        self.best_lap_ticks: Optional[int] = None
        self.current_lap = 0

    def to_dict(self):
        return {
            "playerId": self.player_id,
            "name": self.name,
            "teamId": self.team_id,
            "carModel": self.car_model,
            "carColor": self.car_color,
            "driverId": self.driver_id,
            "isSpectator": self.is_spectator,
            "isHost": self.is_host,
            "ready": self.ready,
            "slot": self.slot,
            "finished": self.finished,
            "finishTimeTicks": self.finish_time_ticks,
            "bestLapTicks": self.best_lap_ticks,
            "currentLap": self.current_lap,
        }

class GameRoom:
    def __init__(
        self,
        room_id: str,
        name: str,
        track_id: str,
        laps: int,
        weather: str,
        collision: str,
        max_players: int,
        is_public: bool,
    ):
        self.room_id = room_id
        self.name = name
        self.track_id = track_id
        self.laps = laps
        self.weather = weather
        self.collision = collision
        self.max_players = max_players
        self.is_public = is_public
        self.status = "lobby"  # lobby | countdown | racing | finished
        self.created_at = time.time()
        self.host_id = ""
        self.players: Dict[str, ConnectedPlayer] = {}
        self.chat_history: List[dict] = []
        self.race_start_timestamp_ms: Optional[float] = None
        self.lock = asyncio.Lock()

    def get_summary(self) -> RoomSummary:
        racers = [p for p in self.players.values() if not p.is_spectator]
        spectators = [p for p in self.players.values() if p.is_spectator]
        host = self.players.get(self.host_id)
        host_name = host.name if host else "Unknown"
        return RoomSummary(
            room_id=self.room_id,
            room_name=self.name,
            track_id=self.track_id,
            laps=self.laps,
            weather=self.weather,
            collision=self.collision,
            player_count=len(racers),
            spectator_count=len(spectators),
            max_players=self.max_players,
            status=self.status,
            host_name=host_name,
            created_at=self.created_at,
        )

    def to_state_dict(self):
        return {
            "roomId": self.room_id,
            "roomName": self.name,
            "trackId": self.track_id,
            "laps": self.laps,
            "weather": self.weather,
            "collision": self.collision,
            "maxPlayers": self.max_players,
            "status": self.status,
            "hostId": self.host_id,
            "players": [p.to_dict() for p in self.players.values()],
            "raceStartTimestampMs": self.race_start_timestamp_ms,
        }

    async def broadcast(self, message: dict, exclude_id: Optional[str] = None):
        dead_ids = []
        msg_str = json.dumps(message)
        for pid, player in list(self.players.items()):
            if exclude_id and pid == exclude_id:
                continue
            if player.ws:
                try:
                    await player.ws.send_text(msg_str)
                except Exception:
                    dead_ids.append(pid)
        for pid in dead_ids:
            await self.remove_player(pid)

    async def add_player(self, player: ConnectedPlayer):
        async with self.lock:
            if not self.host_id:
                self.host_id = player.player_id
                player.is_host = True
                player.ready = True
            self.players[player.player_id] = player
            self.assign_slots()

    async def remove_player(self, player_id: str):
        async with self.lock:
            if player_id in self.players:
                removed = self.players.pop(player_id)
                logger.info(f"Player {removed.name} ({player_id}) left room {self.room_id}")
                if self.host_id == player_id and self.players:
                    # Pass host to next active player
                    next_host = next((p for p in self.players.values() if not p.is_spectator), None)
                    if not next_host and self.players:
                        next_host = next(iter(self.players.values()))
                    if next_host:
                        self.host_id = next_host.player_id
                        next_host.is_host = True
                        next_host.ready = True
                self.assign_slots()
                await self.broadcast({
                    "type": "PLAYER_LEFT",
                    "playerId": player_id,
                    "roomState": self.to_state_dict(),
                })

    def assign_slots(self):
        """Assign grid starting slot indices to all non-spectators (0 = Pole, 1 = P2, etc.)"""
        racers = [p for p in self.players.values() if not p.is_spectator]
        for slot_idx, racer in enumerate(racers):
            racer.slot = slot_idx


# In-memory room storage
rooms: Dict[str, GameRoom] = {}

def generate_room_code() -> str:
    letters = "".join(random.choices(string.ascii_uppercase, k=4))
    digits = "".join(random.choices(string.digits, k=2))
    code = f"{letters}{digits}"
    while code in rooms:
        code = f"{''.join(random.choices(string.ascii_uppercase, k=4))}{''.join(random.choices(string.digits, k=2))}"
    return code


# ----------------- HTTP REST Endpoints -----------------
@router.get("/rooms", response_model=List[RoomSummary])
async def list_rooms():
    """List active public rooms that are still accepting players."""
    now = time.time()
    # Clean up empty or stale rooms older than 3 hours
    stale_ids = [
        rid for rid, r in rooms.items()
        if len(r.players) == 0 or (now - r.created_at > 10800)
    ]
    for rid in stale_ids:
        rooms.pop(rid, None)

    return [r.get_summary() for r in rooms.values() if r.is_public]


@router.post("/rooms")
async def create_room(req: CreateRoomRequest):
    """Create a new multiplayer racing room."""
    room_id = generate_room_code()
    room = GameRoom(
        room_id=room_id,
        name=req.room_name,
        track_id=req.track_id,
        laps=req.laps,
        weather=req.weather,
        collision=req.collision,
        max_players=req.max_players,
        is_public=req.is_public,
    )
    rooms[room_id] = room
    return {"success": True, "roomId": room_id, "summary": room.get_summary().model_dump()}


@router.get("/rooms/{room_id}")
async def get_room(room_id: str):
    """Get full state for a specific room."""
    room_id_upper = room_id.upper()
    room = rooms.get(room_id_upper)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.to_state_dict()


# ----------------- WebSocket Live Racing & Telemetry -----------------
@router.websocket("/ws/{room_id}")
async def multiplayer_ws(websocket: WebSocket, room_id: str):
    room_id_upper = room_id.upper()
    room = rooms.get(room_id_upper)
    if not room:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type": "ERROR", "message": "Room not found"}))
        await websocket.close()
        return

    await websocket.accept()
    current_player_id: Optional[str] = None

    try:
        while True:
            text = await websocket.receive_text()
            data = json.loads(text)
            msg_type = data.get("type")

            # 1. Join Room
            if msg_type == "JOIN":
                current_player_id = data.get("playerId") or f"p_{int(time.time()*1000)}"
                name = data.get("name") or "Racer"
                team_id = data.get("teamId") or "scuderia"
                car_model = data.get("carModel") or "low_poly_f1"
                car_color = data.get("carColor") or "#e10600"
                driver_id = data.get("driverId") or "apex"
                is_spectator = bool(data.get("isSpectator", False))

                player = ConnectedPlayer(
                    player_id=current_player_id,
                    name=name,
                    team_id=team_id,
                    car_model=car_model,
                    car_color=car_color,
                    driver_id=driver_id,
                    is_spectator=is_spectator,
                    ws=websocket,
                )
                await room.add_player(player)

                # Send initial state to the joiner
                await websocket.send_text(json.dumps({
                    "type": "JOIN_SUCCESS",
                    "yourPlayerId": current_player_id,
                    "roomState": room.to_state_dict(),
                }))

                # Broadcast to others
                await room.broadcast({
                    "type": "PLAYER_JOINED",
                    "player": player.to_dict(),
                    "roomState": room.to_state_dict(),
                }, exclude_id=current_player_id)

            # 2. Toggle Ready Status
            elif msg_type == "SET_READY":
                if current_player_id and current_player_id in room.players:
                    player = room.players[current_player_id]
                    player.ready = bool(data.get("ready", True))
                    await room.broadcast({
                        "type": "PLAYER_READY_CHANGED",
                        "playerId": current_player_id,
                        "ready": player.ready,
                        "roomState": room.to_state_dict(),
                    })

            # 3. Update Car / Livery Settings
            elif msg_type == "UPDATE_PREFS":
                if current_player_id and current_player_id in room.players:
                    player = room.players[current_player_id]
                    if "carModel" in data: player.car_model = data["carModel"]
                    if "carColor" in data: player.car_color = data["carColor"]
                    if "name" in data: player.name = data["name"]
                    if "teamId" in data: player.team_id = data["teamId"]
                    await room.broadcast({
                        "type": "PLAYER_PREFS_CHANGED",
                        "playerId": current_player_id,
                        "player": player.to_dict(),
                    })

            # 4. Host Launches Race
            elif msg_type == "START_RACE":
                if current_player_id and current_player_id == room.host_id:
                    room.status = "racing"
                    room.assign_slots()
                    # Start countdown with precise server synchronized timestamp (4.5s countdown)
                    start_at_ms = (time.time() + 4.5) * 1000
                    room.race_start_timestamp_ms = start_at_ms
                    await room.broadcast({
                        "type": "RACE_STARTING",
                        "startAtTimestampMs": start_at_ms,
                        "roomState": room.to_state_dict(),
                    })

            # 5. Live In-Race Telemetry Sync (Dead Reckoning & Lerp)
            elif msg_type == "PLAYER_STATE":
                if current_player_id and current_player_id in room.players:
                    player = room.players[current_player_id]
                    player.last_seen = time.time()
                    state_data = data.get("state", {})
                    player.telemetry = state_data
                    if "lap" in state_data:
                        player.current_lap = state_data["lap"]
                    # Relay to all others immediately
                    await room.broadcast({
                        "type": "REMOTE_STATE",
                        "playerId": current_player_id,
                        "state": state_data,
                    }, exclude_id=current_player_id)

            # 6. Mutual Collision Event
            elif msg_type == "COLLISION_EVENT":
                target_id = data.get("targetPlayerId")
                hit_speed = data.get("hitSpeed", 100)
                nx = data.get("nx", 0)
                ny = data.get("ny", 0)
                x = data.get("x", 0)
                y = data.get("y", 0)
                # Broadcast collision impact to room so players and spectators see sparks & debris
                await room.broadcast({
                    "type": "COLLISION_IMPACT",
                    "sourcePlayerId": current_player_id,
                    "targetPlayerId": target_id,
                    "hitSpeed": hit_speed,
                    "nx": nx,
                    "ny": ny,
                    "x": x,
                    "y": y,
                })

            # 7. Lap Completed / Race Finished
            elif msg_type == "LAP_COMPLETED":
                if current_player_id and current_player_id in room.players:
                    player = room.players[current_player_id]
                    player.current_lap = data.get("lap", player.current_lap)
                    lap_ticks = data.get("lapTicks")
                    if lap_ticks:
                        if player.best_lap_ticks is None or lap_ticks < player.best_lap_ticks:
                            player.best_lap_ticks = lap_ticks
                    await room.broadcast({
                        "type": "REMOTE_LAP_COMPLETED",
                        "playerId": current_player_id,
                        "lap": player.current_lap,
                        "lapTicks": lap_ticks,
                        "bestLapTicks": player.best_lap_ticks,
                    })

            elif msg_type == "RACE_FINISHED":
                if current_player_id and current_player_id in room.players:
                    player = room.players[current_player_id]
                    player.finished = True
                    player.finish_time_ticks = data.get("finishTimeTicks")
                    await room.broadcast({
                        "type": "REMOTE_RACE_FINISHED",
                        "playerId": current_player_id,
                        "finishTimeTicks": player.finish_time_ticks,
                        "roomState": room.to_state_dict(),
                    })
                    # Check if all active racers are finished
                    active_racers = [p for p in room.players.values() if not p.is_spectator]
                    if active_racers and all(p.finished for p in active_racers):
                        room.status = "finished"
                        await room.broadcast({
                            "type": "ALL_RACERS_FINISHED",
                            "roomState": room.to_state_dict(),
                        })

            # 8. Radio / Chat Messages
            elif msg_type == "CHAT_MESSAGE":
                if current_player_id and current_player_id in room.players:
                    sender = room.players[current_player_id]
                    text_msg = (data.get("text") or "").strip()[:140]
                    is_quick = bool(data.get("isQuick", False))
                    if text_msg:
                        chat_entry = {
                            "playerId": current_player_id,
                            "senderName": sender.name,
                            "senderColor": sender.car_color,
                            "text": text_msg,
                            "isQuick": is_quick,
                            "time": time.time(),
                        }
                        room.chat_history.append(chat_entry)
                        if len(room.chat_history) > 50:
                            room.chat_history.pop(0)
                        await room.broadcast({
                            "type": "NEW_CHAT",
                            "chat": chat_entry,
                        })

            # 9. Latency Ping / Pong
            elif msg_type == "PING":
                client_t = data.get("t", 0)
                await websocket.send_text(json.dumps({
                    "type": "PONG",
                    "t": client_t,
                    "serverTime": time.time() * 1000,
                }))

    except WebSocketDisconnect:
        if current_player_id:
            await room.remove_player(current_player_id)
    except Exception as e:
        logger.warning(f"WebSocket error in room {room_id}: {e}")
        if current_player_id:
            await room.remove_player(current_player_id)

