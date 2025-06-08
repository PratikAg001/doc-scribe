import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List
from openai import AzureOpenAI
from config.settings import settings
from models.soap import SOAPResponse

logger = logging.getLogger(__name__)

class SOAPGeneratorService:
    """Handles SOAP note generation using Azure OpenAI with source mapping"""
    
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint
        )
        self.model = settings.azure_openai_deployment_name
    
    async def generate_soap_note(self, transcript: str) -> Dict[str, Any]:
        """
        Generate SOAP note with source mapping from transcript
        
        Args:
            transcript: The complete conversation transcript
            
        Returns:
            Dictionary containing SOAP note, sections, and transcript segments
        """
        try:
            start_time = datetime.now()
            
            # Split transcript into segments for citation
            transcript_segments = self._split_transcript_into_segments(transcript)
            
            # Generate SOAP note with source mapping
            soap_data = await self._generate_structured_soap(transcript_segments)
            
            # Add source text to each statement
            self._add_source_text_to_statements(soap_data["soap_sections"], transcript_segments)
            
            # Add metadata
            soap_data["transcript_segments"] = transcript_segments
            soap_data["generation_time"] = (datetime.now() - start_time).total_seconds()
            soap_data["model_used"] = self.model
            
            return soap_data
            
        except Exception as e:
            logger.error(f"SOAP generation failed: {e}")
            # Return fallback structure
            return {
                "soap_note": f"Error generating SOAP note: {str(e)}",
                "soap_sections": {},
                "transcript_segments": self._split_transcript_into_segments(transcript),
                "generation_time": 0,
                "model_used": self.model
            }
    
    async def _generate_structured_soap(self, transcript_segments: List[str]) -> Dict[str, Any]:
        """Generate structured SOAP note with source citations"""
        
        # Format transcript with segment numbers
        formatted_transcript = self._format_transcript_with_segments(transcript_segments)
        
        soap_prompt = f"""
You are an expert medical scribe. Based on the following doctor-patient conversation transcript, generate a comprehensive SOAP note WITH SOURCE CITATIONS.

TRANSCRIPT (with segment numbers):
{formatted_transcript}

INSTRUCTIONS:
1. Generate a complete SOAP note with these sections:
   - SUBJECTIVE (S): Patient's symptoms, history, complaints
   - OBJECTIVE (O): Physical exam findings, vital signs  
   - ASSESSMENT (A): Clinical impression, diagnosis
   - PLAN (P): Treatment plan, follow-up

2. For EACH statement in your SOAP note, provide the segment number(s) from the transcript that support that statement.

3. Format your response as JSON with this exact structure:
{{
  "soap_note": "Complete SOAP note text here...",
  "soap_sections": {{
    "subjective": [
      {{
        "statement": "Patient reports chest pain for 2 days",
        "source_segments": [1, 3],
        "confidence": 0.95
      }}
    ],
    "objective": [
      {{
        "statement": "Blood pressure 140/90 mmHg",
        "source_segments": [7],
        "confidence": 0.99
      }}
    ],
    "assessment": [
      {{
        "statement": "Hypertension, uncontrolled",
        "source_segments": [7, 12],
        "confidence": 0.85
      }}
    ],
    "plan": [
      {{
        "statement": "Start lisinopril 10mg daily",
        "source_segments": [15],
        "confidence": 0.90
      }}
    ]
  }}
}}

Make sure to:
- Include confidence scores (0.0-1.0) for how well each statement is supported by the source
- Reference specific segment numbers that support each statement
- Use proper medical terminology
- Be thorough but concise
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert medical scribe. Always respond with valid JSON."},
                    {"role": "user", "content": soap_prompt}
                ],
                max_tokens=3000,
                temperature=0.2
            )
            
            # Parse JSON response
            soap_data = json.loads(response.choices[0].message.content)
            return soap_data
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from SOAP response: {e}")
            # Fallback: create basic structure
            return {
                "soap_note": response.choices[0].message.content,
                "soap_sections": {}
            }
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise
    
    def _split_transcript_into_segments(self, transcript: str) -> List[str]:
        """Split transcript into meaningful segments for citation"""
        if not transcript:
            return []
        
        # Split by sentence boundaries, keeping segments reasonably sized
        sentences = re.split(r'[.!?]+\s+', transcript)
        segments = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                # If sentence is very long, split further
                if len(sentence) > 200:
                    # Split by pauses, commas, or other natural breaks
                    sub_segments = re.split(r'[,;]\s+|\s+and\s+|\s+but\s+|\s+so\s+', sentence)
                    for sub_seg in sub_segments:
                        sub_seg = sub_seg.strip()
                        if sub_seg and len(sub_seg) > 10:  # Ignore very short fragments
                            segments.append(sub_seg)
                else:
                    segments.append(sentence)
        
        return segments
    
    def _format_transcript_with_segments(self, segments: List[str]) -> str:
        """Format transcript with segment numbers for AI reference"""
        formatted_segments = []
        for i, segment in enumerate(segments, 1):
            formatted_segments.append(f"[{i}] {segment}")
        
        return "\n".join(formatted_segments)
    
    def _add_source_text_to_statements(self, soap_sections: Dict[str, Any], transcript_segments: List[str]) -> None:
        """Add actual source text to each SOAP statement"""
        for section_name, statements in soap_sections.items():
            for statement in statements:
                source_text_parts = []
                for segment_num in statement.get("source_segments", []):
                    if 1 <= segment_num <= len(transcript_segments):
                        source_text_parts.append(transcript_segments[segment_num - 1])
                statement["source_text"] = " ... ".join(source_text_parts)
    
    def get_generation_stats(self) -> dict:
        """Get SOAP generation service statistics"""
        return {
            "service": "Azure OpenAI",
            "model": self.model,
            "api_version": settings.azure_openai_api_version,
            "features": [
                "Source mapping",
                "Confidence scoring",
                "Structured output",
                "Medical terminology"
            ]
        }
