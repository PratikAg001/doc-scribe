import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from database.connection import get_database
from services.session_manager import get_session_manager
from services.processing_pool import get_processing_pool
from api.routes import sessions_router, feedback_router, websocket_router
from utils.helpers import setup_logging, get_system_info

# Setup logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    try:
        # Initialize database connection
        await get_database()
        print("✅ Database connected successfully")
        
        # Initialize session manager
        session_mgr = await get_session_manager()
        await session_mgr.start_manager()
        print("✅ Session manager started")
        
        # Initialize processing pool
        processing_pool = await get_processing_pool()
        await processing_pool.start_pool()
        print("✅ Audio processing pool started")
        
        # Initialize services
        print("✅ Services initialized")
        
        print("🚀 AI Medical Scribe API started successfully")
        
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    try:
        # Stop processing pool
        processing_pool = await get_processing_pool()
        await processing_pool.stop_pool()
        print("✅ Audio processing pool stopped")
        
        # Stop session manager
        session_mgr = await get_session_manager()
        await session_mgr.stop_manager()
        print("✅ Session manager stopped")
        
        # Close database connections
        db = await get_database()
        await db.disconnect()
        print("✅ Database disconnected")
        
        print("🛑 AI Medical Scribe API shutdown complete")
        
    except Exception as e:
        print(f"⚠️ Shutdown warning: {e}")

# Create FastAPI application
app = FastAPI(
    title="AI Medical Scribe API",
    description="Advanced AI-powered medical scribe system with real-time transcription and SOAP note generation",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sessions_router)
app.include_router(feedback_router) 
app.include_router(websocket_router)

@app.get("/")
async def root():
    """Root endpoint with system information"""
    return {
        "message": "AI Medical Scribe System API - Refactored Architecture",
        "status": "active",
        "system_info": get_system_info(),
        "features": [
            "Real-time audio transcription",
            "Multi-mode audio processing",
            "SOAP note generation with source mapping",
            "Clinician feedback loop",
            "Learning analytics",
            "Scalable architecture"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db = await get_database()
        await db.database.command("ping")
        
        return {
            "status": "healthy",
            "timestamp": get_system_info()["timestamp"],
            "services": {
                "database": "connected",
                "api": "active",
                "transcription": "ready",
                "soap_generation": "ready"
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": get_system_info()["timestamp"],
                "error": str(e)
            }
        )

@app.get("/api/processing-stats")
async def get_processing_stats():
    """Get detailed processing statistics for monitoring"""
    try:
        # Get session manager stats
        session_mgr = await get_session_manager()
        session_stats = await session_mgr.get_stats()
        
        # Get processing pool stats
        processing_pool = await get_processing_pool()
        processing_stats = processing_pool.get_stats()
        
        return {
            "session_management": session_stats,
            "audio_processing": processing_stats,
            "system_health": {
                "concurrent_capacity": f"{session_stats['active_sessions']}/{settings.max_concurrent_sessions}",
                "memory_usage_mb": session_stats.get("memory_usage_mb", 0) + (processing_stats.get("memory_usage_mb", 0)),
                "avg_processing_time": processing_stats.get("avg_processing_time", 0),
                "task_success_rate": (
                    processing_stats["completed_tasks"] / max(processing_stats["total_tasks"], 1) * 100
                ) if processing_stats["total_tasks"] > 0 else 100
            },
            "performance_metrics": {
                "total_sessions_processed": session_stats["total_sessions"],
                "peak_concurrent_sessions": session_stats["peak_concurrent"],
                "total_audio_tasks": processing_stats["total_tasks"],
                "failed_tasks": processing_stats["failed_tasks"],
                "active_processing_tasks": processing_stats["queue_size"]
            }
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Failed to retrieve processing stats",
                "message": str(e)
            }
        )

@app.get("/api/system-info")
async def get_api_system_info():
    """Get detailed system information"""
    return {
        "system": get_system_info(),
        "configuration": {
            "max_concurrent_sessions": settings.max_concurrent_sessions,
            "audio_sample_rate": settings.audio_sample_rate,
            "transcription_interval": f"{settings.transcription_interval_chunks} chunks",
            "database_pool_size": settings.db_connection_pool_size
        },
        "services": {
            "transcription": "Deepgram (nova-2)",
            "soap_generation": "Azure OpenAI",
            "database": "MongoDB",
            "audio_processing": "Multi-mode (standard/enhanced)"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )