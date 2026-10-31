from typing import Optional
from pydantic import BaseModel


class MusicTrackItem(BaseModel):
    id: str
    title: str
    artist: str
    duration: int
    streamUrl: str
    proxyUrl: Optional[str] = None
    isActive: bool = True


class PresignedUploadRequest(BaseModel):
    filename: str
    contentType: str = "audio/mpeg"
    category: str = "music"  # 'music', 'models', 'ghosts'


class PresignedUploadResponse(BaseModel):
    uploadUrl: str
    publicUrl: str
    key: str

