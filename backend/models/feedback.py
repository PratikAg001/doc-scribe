from typing import Optional, List
from pydantic import BaseModel, Field

class EditFeedback(BaseModel):
    """Model for individual edit feedback"""
    section: str = Field(..., description="SOAP section: subjective, objective, assessment, plan")
    statement_index: int = Field(..., ge=0, description="Index of the statement being edited")
    original_text: str = Field(..., min_length=1, description="Original AI-generated text")
    edited_text: str = Field(..., min_length=1, description="Clinician-edited text")
    edit_type: str = Field(..., description="Type of edit: factual_correction, style_improvement, addition, deletion")
    confidence_rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="Clinician confidence rating 1-5")

class SessionFeedback(BaseModel):
    """Model for complete session feedback"""
    session_id: str = Field(..., description="Session identifier")
    edits: List[EditFeedback] = Field(default_factory=list, description="List of edits made")
    overall_satisfaction: float = Field(..., ge=1.0, le=5.0, description="Overall satisfaction rating 1-5")
    time_saved_minutes: Optional[float] = Field(None, ge=0, description="Time saved in minutes")
    comments: Optional[str] = Field(None, description="Additional comments")

class FeedbackResponse(BaseModel):
    """Model for feedback submission response"""
    message: str
    edits_count: int
    learning_status: str
    feedback_id: Optional[str] = None
