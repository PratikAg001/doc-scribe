"""
Real-time Deepgram Streaming Service
Implements WebSocket-to-WebSocket streaming for minimal latency
"""

import asyncio
import json
import logging
import websockets
from typing import Optional, Callable
from config.settings import settings

logger = logging.getLogger(__name__)

class DeepgramStreamingClient:
    """Real-time streaming client for Deepgram WebSocket API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.is_connected = False
        self.transcription_callback: Optional[Callable] = None
        
    async def connect(self):
        """Connect to Deepgram real-time streaming API"""
        try:
            # Deepgram streaming endpoint
            url = f"wss://api.deepgram.com/v1/listen?model=nova-2&language=en&punctuate=true&interim_results=true&endpointing=300&smart_format=true"
            
            headers = {
                "Authorization": f"Token {self.api_key}"
            }
            
            self.websocket = await websockets.connect(url, extra_headers=headers)
            self.is_connected = True
            
            logger.info("🎤 Connected to Deepgram real-time streaming")
            
            # Start listening for responses
            asyncio.create_task(self._listen_for_responses())
            
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram streaming: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self):
        """Disconnect from Deepgram streaming API"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.close()
                self.is_connected = False
                logger.info("🔌 Disconnected from Deepgram streaming")
        except Exception as e:
            logger.error(f"Error disconnecting from Deepgram: {e}")
    
    async def send_audio(self, audio_data: bytes):
        """Send audio data to Deepgram for real-time transcription"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.send(audio_data)
            else:
                logger.warning("Cannot send audio: not connected to Deepgram")
        except Exception as e:
            logger.error(f"Error sending audio to Deepgram: {e}")
            self.is_connected = False
    
    async def _listen_for_responses(self):
        """Listen for transcription responses from Deepgram"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    
                    if data.get("type") == "Results":
                        alternatives = data.get("channel", {}).get("alternatives", [])
                        if alternatives:
                            transcript = alternatives[0].get("transcript", "")
                            is_final = data.get("is_final", False)
                            confidence = alternatives[0].get("confidence", 0.0)
                            
                            if transcript.strip() and self.transcription_callback:
                                await self.transcription_callback({
                                    "transcript": transcript,
                                    "is_final": is_final,
                                    "confidence": confidence,
                                    "type": "real_time_stream"
                                })
                    
                    elif data.get("type") == "Metadata":
                        logger.info(f"Deepgram metadata: {data}")
                        
                    elif data.get("type") == "SpeechStarted":
                        logger.info("🎙️ Speech started")
                        
                    elif data.get("type") == "UtteranceEnd":
                        logger.info("🏁 Utterance ended")
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from Deepgram: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info("Deepgram WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error listening to Deepgram responses: {e}")
            self.is_connected = False
    
    def set_transcription_callback(self, callback: Callable):
        """Set callback function for transcription results"""
        self.transcription_callback = callback
    
    async def finalize_stream(self):
        """Send finalization message to get final results"""
        try:
            if self.websocket and self.is_connected:
                # Send close frame to indicate end of audio
                await self.websocket.send(json.dumps({"type": "CloseStream"}))
                logger.info("📝 Sent stream finalization to Deepgram")
        except Exception as e:
            logger.error(f"Error finalizing stream: {e}")


class StreamingTranscriptionPool:
    """Pool manager for real-time streaming connections"""
    
    def __init__(self):
        self.active_streams: dict[str, DeepgramStreamingClient] = {}
        self.api_key = settings.deepgram_api_key
    
    async def create_stream(self, session_id: str, transcription_callback: Callable) -> DeepgramStreamingClient:
        """Create a new streaming connection for a session"""
        try:
            if session_id in self.active_streams:
                await self.close_stream(session_id)
            
            client = DeepgramStreamingClient(self.api_key)
            client.set_transcription_callback(transcription_callback)
            
            await client.connect()
            self.active_streams[session_id] = client
            
            logger.info(f"🚀 Created real-time stream for session {session_id}")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create stream for {session_id}: {e}")
            raise
    
    async def close_stream(self, session_id: str):
        """Close streaming connection for a session"""
        try:
            if session_id in self.active_streams:
                client = self.active_streams[session_id]
                await client.finalize_stream()
                await client.disconnect()
                del self.active_streams[session_id]
                logger.info(f"🔌 Closed real-time stream for session {session_id}")
        except Exception as e:
            logger.error(f"Error closing stream for {session_id}: {e}")
    
    async def get_stream(self, session_id: str) -> Optional[DeepgramStreamingClient]:
        """Get existing stream for a session"""
        return self.active_streams.get(session_id)
    
    async def cleanup_all_streams(self):
        """Close all active streams (for shutdown)"""
        for session_id in list(self.active_streams.keys()):
            await self.close_stream(session_id)
        logger.info("🧹 Cleaned up all streaming connections")

# Global streaming pool instance
_streaming_pool: Optional[StreamingTranscriptionPool] = None

async def get_streaming_pool() -> StreamingTranscriptionPool:
    """Get global streaming pool instance"""
    global _streaming_pool
    if _streaming_pool is None:
        _streaming_pool = StreamingTranscriptionPool()
    return _streaming_pool