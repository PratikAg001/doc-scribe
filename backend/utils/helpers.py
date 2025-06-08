import logging
import sys
import platform
from datetime import datetime
from typing import Dict, Any
from config.settings import settings

def setup_logging() -> None:
    """Configure application logging"""
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    
    logging.info("Logging configured successfully")

def get_system_info() -> Dict[str, Any]:
    """Get system information for health checks"""
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor(),
        "timestamp": datetime.now().isoformat(),
        "application": "AI Medical Scribe",
        "version": "1.0.0",
        "environment": "development" if settings.debug else "production"
    }

def validate_session_id(session_id: str) -> bool:
    """Validate session ID format"""
    import uuid
    try:
        uuid.UUID(session_id)
        return True
    except ValueError:
        return False

def sanitize_transcript(transcript: str) -> str:
    """Sanitize transcript for processing"""
    if not transcript:
        return ""
    
    # Basic sanitization
    transcript = transcript.strip()
    
    # Remove excessive whitespace
    import re
    transcript = re.sub(r'\s+', ' ', transcript)
    
    return transcript

def calculate_audio_duration(chunk_count: int) -> float:
    """Calculate audio duration from chunk count"""
    return chunk_count * 0.064  # 64ms per chunk

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def get_audio_stats(audio_data: bytes) -> Dict[str, Any]:
    """Get basic audio statistics"""
    return {
        "size_bytes": len(audio_data),
        "size_kb": len(audio_data) / 1024,
        "estimated_duration": len(audio_data) / (settings.audio_sample_rate * 2),  # 16-bit = 2 bytes
        "sample_rate": settings.audio_sample_rate,
        "channels": 1,  # Mono
        "bit_depth": 16
    }
