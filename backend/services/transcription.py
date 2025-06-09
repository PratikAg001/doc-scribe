import logging
import tempfile
import os
from typing import Optional
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from config.settings import settings

logger = logging.getLogger(__name__)

class TranscriptionService:
    """Handles audio transcription using Deepgram API"""
    
    def __init__(self):
        self.client = DeepgramClient(settings.deepgram_api_key)
        self._chunk_options = PrerecordedOptions(
            model="nova-3-medical",
            smart_format=True,
            punctuate=True,
        )
        self._final_options = PrerecordedOptions(
            model="nova-3-medical",
            smart_format=True,
            utterances=True,
            punctuate=True,
            diarize=True,
        )
    
    async def transcribe_audio_chunk(self, audio_data: bytes) -> str:
        """
        Transcribe a small audio chunk for real-time feedback
        
        Args:
            audio_data: Raw audio bytes
            
        Returns:
            Transcribed text or empty string if no speech detected
        """
        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                self._write_wav_header(temp_file, audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Read file and prepare for Deepgram
                with open(temp_file_path, "rb") as file:
                    buffer_data = file.read()
                
                payload: FileSource = {"buffer": buffer_data}
                
                # Transcribe
                response = self.client.listen.prerecorded.v("1").transcribe_file(
                    payload, self._chunk_options
                )
                
                # Extract transcript
                if response.results and response.results.channels:
                    transcript = response.results.channels[0].alternatives[0].transcript
                    print(transcript)
                    return transcript or ""
                else:
                    return ""
                    
            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"Chunk transcription error: {e}")
            return ""
    
    async def transcribe_complete_audio(self, audio_data: bytes) -> str:
        """
        Transcribe complete audio file with enhanced options
        
        Args:
            audio_data: Complete audio bytes
            
        Returns:
            Full transcribed text
        """
        try:
            # Create temporary WAV file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                self._write_wav_header(temp_file, audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Read file and prepare for Deepgram
                with open(temp_file_path, "rb") as file:
                    buffer_data = file.read()
                
                payload: FileSource = {"buffer": buffer_data}
                
                # Transcribe with enhanced options
                response = self.client.listen.prerecorded.v("1").transcribe_file(
                    payload, self._final_options
                )
                
                # Extract transcript
                if response.results and response.results.channels:
                    transcript = response.results.channels[0].alternatives[0].transcript
                    print(transcript)
                    return transcript or ""
                else:
                    return ""
                    
            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"Complete transcription error: {e}")
            return ""
    
    def _write_wav_header(self, file_handle, audio_data: bytes) -> None:
        """Write WAV file header for raw PCM data"""
        import wave
        
        with wave.open(file_handle.name, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(settings.audio_sample_rate)  # Sample rate from config
            wav_file.writeframes(audio_data)
    
    def get_transcription_stats(self) -> dict:
        """Get transcription service statistics"""
        return {
            "service": "Deepgram",
            "model": "nova-3-medical",
            "sample_rate": settings.audio_sample_rate,
            "chunk_options": {
                "smart_format": True,
                "punctuate": True
            },
            "final_options": {
                "smart_format": True,
                "utterances": True,
                "punctuate": True,
                "diarize": True
            }
        }
