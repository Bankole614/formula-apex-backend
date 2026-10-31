from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


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


class ConnectedPlayerState(BaseModel):
    playerId: str
    name: str
    teamId: str
    carModel: str
    carColor: str
    driverId: str
    isSpectator: bool
    isHost: bool
    ready: bool
    slot: int
    finished: bool
    finishTimeTicks: Optional[int] = None
    bestLapTicks: Optional[int] = None
    currentLap: int


class RoomStateResponse(BaseModel):
    roomId: str
    roomName: str
    trackId: str
    laps: int
    weather: str
    collision: str
    maxPlayers: int
    status: str
    hostId: str
    players: List[ConnectedPlayerState]
    raceStartTimestampMs: Optional[float] = None

