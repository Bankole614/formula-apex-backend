"""
Database & API Models / Schemas.
For domain-separated schemas, prefer importing from `app.schemas`.
This file preserves backward compatibility.
"""
from app.schemas import (
    LeaderboardSubmission,
    LeaderboardEntryResponse,
    CommunityTrackSubmission,
    CommunityTrackResponse,
    CareerSyncRequest,
    CareerProfileResponse,
    MusicTrackItem,
    PresignedUploadRequest,
    PresignedUploadResponse,
    CreateRoomRequest,
    RoomSummary,
    RoomStateResponse,
    ConnectedPlayerState,
)

__all__ = [
    "LeaderboardSubmission",
    "LeaderboardEntryResponse",
    "CommunityTrackSubmission",
    "CommunityTrackResponse",
    "CareerSyncRequest",
    "CareerProfileResponse",
    "MusicTrackItem",
    "PresignedUploadRequest",
    "PresignedUploadResponse",
    "CreateRoomRequest",
    "RoomSummary",
    "RoomStateResponse",
    "ConnectedPlayerState",
]
