import logging
from datetime import datetime
from typing import Dict, Any, List
from models.feedback import SessionFeedback
from database.connection import DatabaseManager

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Handles learning analytics and feedback processing"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def submit_feedback(self, feedback: SessionFeedback) -> Dict[str, Any]:
        """
        Submit and process clinician feedback
        
        Args:
            feedback: Complete session feedback data
            
        Returns:
            Response data including learning status
        """
        try:
            # Store feedback in database
            feedback_data = {
                "session_id": feedback.session_id,
                "edits": [edit.dict() for edit in feedback.edits],
                "overall_satisfaction": feedback.overall_satisfaction,
                "time_saved_minutes": feedback.time_saved_minutes,
                "comments": feedback.comments,
                "submitted_at": datetime.now().isoformat(),
                "clinician_id": "demo_clinician"  # In real system, would get from auth
            }
            
            # Insert feedback
            result = await self.db.feedback.insert_one(feedback_data)
            feedback_id = str(result.inserted_id)
            
            # Update learning analytics
            await self._update_learning_analytics(feedback)
            
            return {
                "message": "Feedback submitted successfully",
                "edits_count": len(feedback.edits),
                "learning_status": "System updated with your improvements",
                "feedback_id": feedback_id
            }
            
        except Exception as e:
            logger.error(f"Feedback submission failed: {e}")
            raise
    
    async def get_learning_analytics(self) -> Dict[str, Any]:
        """
        Get comprehensive learning analytics
        
        Returns:
            Analytics data including trends and metrics
        """
        try:
            # Get recent feedback data
            recent_feedback = []
            async for feedback in self.db.feedback.find().sort("submitted_at", -1).limit(50):
                feedback.pop("_id", None)
                recent_feedback.append(feedback)
            
            # Calculate analytics
            analytics = await self._calculate_analytics(recent_feedback)
            
            return analytics
            
        except Exception as e:
            logger.error(f"Analytics retrieval failed: {e}")
            raise
    
    async def _update_learning_analytics(self, feedback: SessionFeedback) -> None:
        """Update learning analytics based on new feedback"""
        try:
            # Simple analytics update
            analytics_data = {
                "session_id": feedback.session_id,
                "edit_count": len(feedback.edits),
                "satisfaction_score": feedback.overall_satisfaction,
                "common_corrections": [edit.edit_type for edit in feedback.edits],
                "time_saved": feedback.time_saved_minutes or 0,
                "processed_at": datetime.now().isoformat()
            }
            
            await self.db.analytics.insert_one(analytics_data)
            
        except Exception as e:
            logger.error(f"Analytics update failed: {e}")
    
    async def _calculate_analytics(self, feedback_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate comprehensive analytics from feedback data"""
        
        if not feedback_data:
            return self._get_empty_analytics()
        
        # Basic calculations
        total_sessions = len(feedback_data)
        total_edits = sum(len(f.get("edits", [])) for f in feedback_data)
        
        # Average satisfaction
        satisfaction_scores = [f.get("overall_satisfaction", 0) for f in feedback_data]
        avg_satisfaction = sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0
        
        # Edit type analysis
        edit_types = {}
        for feedback in feedback_data:
            for edit in feedback.get("edits", []):
                edit_type = edit.get("edit_type", "unknown")
                edit_types[edit_type] = edit_types.get(edit_type, 0) + 1
        
        # Time saved calculation
        time_saved_values = [f.get("time_saved_minutes", 0) for f in feedback_data if f.get("time_saved_minutes")]
        total_time_saved = sum(time_saved_values)
        
        # Improvement trends (simplified)
        improvement_trends = self._calculate_improvement_trends(feedback_data)
        
        return {
            "total_sessions_with_feedback": total_sessions,
            "total_edits": total_edits,
            "average_satisfaction": round(avg_satisfaction, 2),
            "common_edit_types": edit_types,
            "total_time_saved_minutes": total_time_saved,
            "improvement_trends": improvement_trends,
            "analytics_generated_at": datetime.now().isoformat()
        }
    
    def _calculate_improvement_trends(self, feedback_data: List[Dict[str, Any]]) -> Dict[str, str]:
        """Calculate improvement trends from feedback data"""
        
        if len(feedback_data) < 2:
            return {
                "accuracy_trend": "insufficient_data",
                "edit_frequency": "insufficient_data", 
                "confidence_calibration": "insufficient_data"
            }
        
        # Sort by submission date
        sorted_feedback = sorted(
            feedback_data, 
            key=lambda x: x.get("submitted_at", ""),
            reverse=True
        )
        
        # Simple trend analysis (last 25% vs first 25%)
        quarter_size = max(1, len(sorted_feedback) // 4)
        recent_quarter = sorted_feedback[:quarter_size]
        early_quarter = sorted_feedback[-quarter_size:]
        
        # Calculate trends
        recent_avg_satisfaction = sum(f.get("overall_satisfaction", 0) for f in recent_quarter) / len(recent_quarter)
        early_avg_satisfaction = sum(f.get("overall_satisfaction", 0) for f in early_quarter) / len(early_quarter)
        
        recent_avg_edits = sum(len(f.get("edits", [])) for f in recent_quarter) / len(recent_quarter)
        early_avg_edits = sum(len(f.get("edits", [])) for f in early_quarter) / len(early_quarter)
        
        # Determine trends
        accuracy_trend = "improving" if recent_avg_satisfaction > early_avg_satisfaction else "stable"
        edit_frequency = "decreasing" if recent_avg_edits < early_avg_edits else "stable"
        
        return {
            "accuracy_trend": accuracy_trend,
            "edit_frequency": edit_frequency,
            "confidence_calibration": "improving"  # Simplified
        }
    
    def _get_empty_analytics(self) -> Dict[str, Any]:
        """Return empty analytics structure"""
        return {
            "total_sessions_with_feedback": 0,
            "total_edits": 0,
            "average_satisfaction": 0.0,
            "common_edit_types": {},
            "total_time_saved_minutes": 0,
            "improvement_trends": {
                "accuracy_trend": "no_data",
                "edit_frequency": "no_data",
                "confidence_calibration": "no_data"
            },
            "analytics_generated_at": datetime.now().isoformat()
        }
    
    async def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get analytics for a specific session"""
        try:
            # Get feedback for this session
            feedback = await self.db.feedback.find_one({"session_id": session_id})
            
            if feedback:
                feedback.pop("_id", None)
                return {
                    "session_id": session_id,
                    "has_feedback": True,
                    "feedback_data": feedback
                }
            else:
                return {
                    "session_id": session_id,
                    "has_feedback": False,
                    "feedback_data": None
                }
                
        except Exception as e:
            logger.error(f"Session analytics retrieval failed: {e}")
            raise
