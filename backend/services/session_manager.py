import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from config.settings import settings

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Scalable session manager with memory-based storage and automatic cleanup
    Designed to handle concurrent sessions efficiently
    """
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats = {
            "total_sessions": 0,
            "active_sessions": 0,
            "peak_concurrent": 0,
            "cleanup_runs": 0
        }
    
    async def start_manager(self):
        """Start the session manager with background cleanup"""
        logger.info("🚀 Starting session manager...")
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"📊 Max concurrent sessions: {settings.max_concurrent_sessions}")
    
    async def stop_manager(self):
        """Stop the session manager and cleanup"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Session manager stopped")
    
    async def create_session(self, session_data: Dict[str, Any]) -> str:
        """
        Create a new session with concurrency limits
        
        Args:
            session_data: Initial session data
            
        Returns:
            session_id: Unique session identifier
            
        Raises:
            RuntimeError: If max concurrent sessions exceeded
        """
        # Check concurrent session limit
        active_count = await self.get_active_session_count()
        if active_count >= settings.max_concurrent_sessions:
            raise RuntimeError(f"Maximum concurrent sessions ({settings.max_concurrent_sessions}) exceeded")
        
        session_id = session_data["session_id"]
        
        # Create session with metadata
        session = {
            **session_data,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "audio_buffer_size": 0,
            "chunk_count": 0,
            "is_active": True
        }
        
        # Thread-safe session creation
        self._session_locks[session_id] = asyncio.Lock()
        async with self._session_locks[session_id]:
            self._sessions[session_id] = session
            self._stats["total_sessions"] += 1
            self._stats["active_sessions"] = len([s for s in self._sessions.values() if s.get("is_active")])
            self._stats["peak_concurrent"] = max(self._stats["peak_concurrent"], self._stats["active_sessions"])
        
        logger.info(f"📝 Created session {session_id} (Active: {self._stats['active_sessions']})")
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data thread-safely"""
        if session_id not in self._sessions:
            return None
        
        lock = self._session_locks.get(session_id)
        if lock:
            async with lock:
                return self._sessions.get(session_id, {}).copy()
        return self._sessions.get(session_id, {}).copy()
    
    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session data thread-safely"""
        if session_id not in self._sessions:
            return False
        
        lock = self._session_locks.get(session_id)
        if lock:
            async with lock:
                self._sessions[session_id].update(updates)
                self._sessions[session_id]["last_activity"] = datetime.now().isoformat()
                return True
        return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session and cleanup resources"""
        if session_id not in self._sessions:
            return False
        
        lock = self._session_locks.get(session_id)
        if lock:
            async with lock:
                if session_id in self._sessions:
                    del self._sessions[session_id]
                if session_id in self._session_locks:
                    del self._session_locks[session_id]
                self._stats["active_sessions"] = len([s for s in self._sessions.values() if s.get("is_active")])
                logger.info(f"🗑️ Deleted session {session_id} (Active: {self._stats['active_sessions']})")
                return True
        return False
    
    async def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        active = []
        for session_id, session in self._sessions.items():
            if session.get("is_active"):
                active.append(session.copy())
        return active
    
    async def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        return len([s for s in self._sessions.values() if s.get("is_active")])
    
    async def mark_session_inactive(self, session_id: str) -> bool:
        """Mark session as inactive but keep for reference"""
        return await self.update_session(session_id, {"is_active": False, "status": "completed"})
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        active_count = await self.get_active_session_count()
        return {
            **self._stats,
            "active_sessions": active_count,
            "total_sessions_stored": len(self._sessions),
            "memory_usage_mb": self._estimate_memory_usage(),
            "avg_buffer_size": self._calculate_avg_buffer_size()
        }
    
    def _estimate_memory_usage(self) -> float:
        """Estimate memory usage in MB (rough calculation)"""
        total_size = 0
        for session in self._sessions.values():
            total_size += session.get("audio_buffer_size", 0)
            total_size += len(str(session)) * 2  # Rough estimate for JSON data
        return total_size / (1024 * 1024)  # Convert to MB
    
    def _calculate_avg_buffer_size(self) -> float:
        """Calculate average audio buffer size across sessions"""
        if not self._sessions:
            return 0.0
        
        total_buffer = sum(s.get("audio_buffer_size", 0) for s in self._sessions.values())
        return total_buffer / len(self._sessions)
    
    async def _cleanup_loop(self):
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(60)  # Run cleanup every minute
                await self._cleanup_inactive_sessions()
                self._stats["cleanup_runs"] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup_inactive_sessions(self):
        """Remove old inactive sessions to free memory"""
        cutoff_time = datetime.now() - timedelta(hours=1)  # Keep sessions for 1 hour
        sessions_to_remove = []
        
        for session_id, session in self._sessions.items():
            if not session.get("is_active"):
                last_activity = datetime.fromisoformat(session.get("last_activity", ""))
                if last_activity < cutoff_time:
                    sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            await self.delete_session(session_id)
        
        if sessions_to_remove:
            logger.info(f"🧹 Cleaned up {len(sessions_to_remove)} inactive sessions")

# Global session manager instance
session_manager = SessionManager()

async def get_session_manager() -> SessionManager:
    """Get session manager instance"""
    return session_manager