from fastapi import APIRouter, HTTPException, Depends
from models.feedback import SessionFeedback, FeedbackResponse
from services.analytics import AnalyticsService
from database.connection import DatabaseManager, get_database

router = APIRouter(prefix="/api", tags=["feedback"])

@router.post("/submit-feedback", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: SessionFeedback,
    db: DatabaseManager = Depends(get_database)
):
    """Submit clinician feedback for a session"""
    try:
        analytics_service = AnalyticsService(db)
        result = await analytics_service.submit_feedback(feedback)
        
        return FeedbackResponse(
            message=result["message"],
            edits_count=result["edits_count"],
            learning_status=result["learning_status"],
            feedback_id=result.get("feedback_id")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Feedback submission failed: {str(e)}")

@router.get("/learning-analytics")
async def get_learning_analytics(db: DatabaseManager = Depends(get_database)):
    """Get learning analytics and system improvement metrics"""
    try:
        analytics_service = AnalyticsService(db)
        analytics = await analytics_service.get_learning_analytics()
        return analytics
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics retrieval failed: {str(e)}")

@router.get("/session/{session_id}/feedback")
async def get_session_feedback(
    session_id: str,
    db: DatabaseManager = Depends(get_database)
):
    """Get feedback data for a specific session"""
    try:
        analytics_service = AnalyticsService(db)
        feedback_data = await analytics_service.get_session_analytics(session_id)
        return feedback_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session feedback retrieval failed: {str(e)}")
