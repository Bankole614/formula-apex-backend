from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class CommunityTrackSubmission(BaseModel):
    name: str = Field(..., min_length=3, max_length=48)
    author: str = Field(..., min_length=2, max_length=32)
    control: List[Dict[str, float]] = Field(..., min_length=4)
    width: Optional[float] = 60.0
    biome: Optional[str] = "temperate"
    pitConfig: Optional[Dict[str, Any]] = None
    scenery: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = "Community custom layout."


class CommunityTrackResponse(BaseModel):
    id: str
    name: str
    author: str
    width: float
    biome: str
    control: List[Dict[str, float]]
    pitConfig: Optional[Dict[str, Any]] = None
    scenery: Optional[List[Dict[str, Any]]] = None
    description: str
    date: str
    likes: int

