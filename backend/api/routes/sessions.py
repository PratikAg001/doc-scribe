import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from models.session import SessionCreate, SessionResponse, SessionUpdate
from database.connection import DatabaseManager, get_database
from services.session_manager import SessionManager, get_session_manager
from config.settings import settings

router = APIRouter(prefix="/api", tags=["sessions"])

@router.post("/start-session", response_model=dict)
async def start_session(
    session_data: Optional[SessionCreate] = None,
    db: DatabaseManager = Depends(get_database),
    session_mgr: SessionManager = Depends(get_session_manager)
):
    """Start a new recording session with concurrency control"""
    try:
        session_id = str(uuid.uuid4())
        
        # Use default processing mode if no data provided
        processing_mode = "standard"
        if session_data:
            processing_mode = session_data.processing_mode
        
        # Create session data
        session = {
            "session_id": session_id,
            "status": "active",
            "processing_mode": processing_mode,
            "transcript": None,
            "soap_note": None,
            "soap_sections": None,
            "transcript_segments": None,
            "processing_time": None
        }
        
        # Create session in scalable session manager
        await session_mgr.create_session(session)
        
        # Store in database for persistence
        session_db = session.copy()
        session_db["created_at"] = datetime.now().isoformat()
        await db.recordings.insert_one(session_db)
        
        return {
            "session_id": session_id,
            "status": "active",
            "message": "Session started successfully"
        }
        
    except RuntimeError as e:
        # Handle max concurrent sessions exceeded
        raise HTTPException(status_code=429, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")

@router.get("/sessions", response_model=List[dict])
async def get_all_sessions(
    db: DatabaseManager = Depends(get_database)
):
    """Get all sessions for session history"""
    try:
        sessions = await db.recordings.find({}).sort("created_at", -1).to_list(100)
        
        # Convert ObjectId to string and clean up the response
        result = []
        for session in sessions:
            session["_id"] = str(session["_id"])
            result.append(session)
            
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve sessions: {str(e)}")

@router.get("/session/{session_id}", response_model=dict)  
async def get_session(
    session_id: str,
    db: DatabaseManager = Depends(get_database)
):
    """Get a specific session by ID"""
    try:
        session = await db.recordings.find_one({"session_id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        session["_id"] = str(session["_id"])
        return session
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve session: {str(e)}")

@router.get("/sessions/stats", response_model=dict)
async def get_session_stats(session_mgr: SessionManager = Depends(get_session_manager)):
    """Get session manager statistics for monitoring"""
    try:
        stats = await session_mgr.get_stats()
        return {
            "session_statistics": stats,
            "health": "healthy" if stats["active_sessions"] < settings.max_concurrent_sessions * 0.8 else "warning"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session stats: {str(e)}")

def get_active_sessions():
    """Legacy function for WebSocket compatibility - will be deprecated"""
    import asyncio
    async def _get_sessions():
        mgr = await get_session_manager()
        return await mgr.get_active_sessions()
    
    # Return empty dict for now - WebSocket will use session manager directly
    return {}
