import asyncio
import logging
from typing import Optional, Dict, Any
from config.settings import settings

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Handles audio processing with different modes and async operations"""
    
    def __init__(self):
        self._processing_cache: Dict[str, Any] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for audio buffers"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up old audio buffers"""
        while True:
            try:
                await asyncio.sleep(settings.audio_buffer_cleanup_interval)
                await self._cleanup_old_buffers()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def _cleanup_old_buffers(self) -> None:
        """Clean up old audio processing caches"""
        # Implementation for cleaning old buffers
        keys_to_remove = []
        for key, data in self._processing_cache.items():
            if self._is_stale(data):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._processing_cache[key]
        
        if keys_to_remove:
            logger.info(f"Cleaned up {len(keys_to_remove)} stale audio buffers")
    
    def _is_stale(self, data: Dict[str, Any]) -> bool:
        """Check if audio buffer data is stale"""
        # Simple staleness check - implement more sophisticated logic as needed
        import time
        return time.time() - data.get('timestamp', 0) > settings.audio_buffer_cleanup_interval
    
    async def process_standard_audio(self, audio_chunk: bytes) -> bytes:
        """Process audio in standard mode (minimal processing)"""
        # Standard mode: return audio as-is for browser-level processing
        return audio_chunk
    
    async def process_enhanced_audio(self, audio_chunk: bytes) -> bytes:
        """Process audio in enhanced mode with noise reduction"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._sync_enhanced_processing, audio_chunk
        )
    
    def _sync_enhanced_processing(self, audio_chunk: bytes) -> bytes:
        """Synchronous enhanced audio processing"""
        try:
            import numpy as np
            import noisereduce as nr
            
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            
            if len(audio_array) < 512:
                return audio_chunk
            
            # Apply noise reduction
            if len(audio_array) > 1024:
                try:
                    reduced_noise = nr.reduce_noise(
                        y=audio_array,
                        sr=settings.audio_sample_rate,
                        prop_decrease=0.7,
                        stationary=True
                    )
                    audio_array = reduced_noise
                except Exception as e:
                    logger.warning(f"Enhanced noise reduction failed: {e}")
            
            # Apply gentle normalization
            rms = np.sqrt(np.mean(audio_array**2))
            if rms > 0:
                audio_array = audio_array * (0.2 / rms)
            
            # Convert back to int16
            final_audio = (audio_array * 32768.0).clip(-32768, 32767).astype(np.int16)
            return final_audio.tobytes()
            
        except Exception as e:
            # logger.error(f"Enhanced audio processing failed: {e}")
            return audio_chunk
    
    async def process_audio_by_mode(self, audio_chunk: bytes, mode: str) -> bytes:
        """Process audio based on the specified mode"""
        if mode == "enhanced":
            return await self.process_enhanced_audio(audio_chunk)
        else:  # standard
            return await self.process_standard_audio(audio_chunk)
