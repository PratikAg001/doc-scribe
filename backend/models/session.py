from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from uuid import uuid4

class SessionCreate(BaseModel):
    """Model for creating a new session"""
    processing_mode: str = "standard"

class SessionUpdate(BaseModel):
    """Model for updating session data"""
    status: Optional[str] = None
    transcript: Optional[str] = None
    soap_note: Optional[str] = None
    soap_sections: Optional[Dict[str, Any]] = None
    transcript_segments: Optional[List[str]] = None
    processing_time: Optional[float] = None
    audio_processing_mode: Optional[str] = None

class SessionResponse(BaseModel):
    """Model for session response data"""
    session_id: str
    status: str
    created_at: str
    transcript: Optional[str] = None
    soap_note: Optional[str] = None
    soap_sections: Optional[Dict[str, Any]] = None
    transcript_segments: Optional[List[str]] = None
    processing_time: Optional[float] = None
    audio_processing_mode: Optional[str] = None
    
class SessionMetadata(BaseModel):
    """Internal session metadata"""
    session_id: str
    created_at: datetime
    last_updated: datetime
    audio_buffer_size: int = 0
    chunk_count: int = 0
    processing_mode: str = "standard"
    is_active: bool = True
