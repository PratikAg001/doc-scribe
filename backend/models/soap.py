from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class SOAPStatement(BaseModel):
    """Individual SOAP statement with source mapping"""
    statement: str = Field(..., description="The SOAP statement text")
    source_segments: List[int] = Field(default_factory=list, description="Source transcript segment numbers")
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI confidence score")
    source_text: Optional[str] = Field(None, description="Actual source text from transcript")

class SOAPSection(BaseModel):
    """SOAP section containing multiple statements"""
    section_name: str = Field(..., description="Section name: subjective, objective, assessment, plan")
    statements: List[SOAPStatement] = Field(default_factory=list, description="List of statements in this section")

class SOAPResponse(BaseModel):
    """Complete SOAP note response with source mapping"""
    soap_note: str = Field(..., description="Complete SOAP note text")
    soap_sections: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict, description="Structured SOAP sections")
    transcript_segments: List[str] = Field(default_factory=list, description="Numbered transcript segments")
    generation_time: Optional[float] = Field(None, description="Time taken to generate SOAP note")
    model_used: Optional[str] = Field(None, description="AI model used for generation")
