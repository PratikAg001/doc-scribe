import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from config.settings import settings

logger = logging.getLogger(__name__)

class AudioProcessingPool:
    """
    Manages concurrent audio processing with worker pools
    Optimized for handling multiple sessions simultaneously
    """
    
    def __init__(self):
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._process_pool: Optional[ProcessPoolExecutor] = None
        self._processing_stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "queue_size": 0,
            "avg_processing_time": 0.0
        }
        self._active_tasks: Dict[str, asyncio.Task] = {}
        
    async def start_pool(self):
        """Initialize worker pools"""
        logger.info("🚀 Starting audio processing pools...")
        
        # Thread pool for I/O-bound operations (transcription API calls)
        self._thread_pool = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_sessions // 2,  # Half for transcription
            thread_name_prefix="AudioProcessor"
        )
        
        # Process pool for CPU-bound operations (audio processing)
        self._process_pool = ProcessPoolExecutor(
            max_workers=min(4, settings.max_concurrent_sessions // 4),  # Quarter for heavy processing
        )
        
        logger.info(f"✅ Audio pools started - Threads: {self._thread_pool._max_workers}, Processes: {self._process_pool._max_workers}")
        
    async def stop_pool(self):
        """Shutdown worker pools gracefully"""
        logger.info("🛑 Stopping audio processing pools...")
        
        # Cancel active tasks
        for task_id, task in self._active_tasks.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled task {task_id}")
        
        # Wait for tasks to complete with timeout
        if self._active_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks.values(), return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some tasks didn't complete within timeout")
        
        # Shutdown pools
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
        if self._process_pool:
            self._process_pool.shutdown(wait=True)
            
        logger.info("✅ Audio processing pools stopped")
    
    async def process_audio_chunk_async(
        self, 
        session_id: str, 
        audio_data: bytes, 
        processing_mode: str
    ) -> bytes:
        """
        Process audio chunk asynchronously without blocking other sessions
        
        Args:
            session_id: Unique session identifier
            audio_data: Raw audio bytes
            processing_mode: Processing mode (standard/enhanced)
            
        Returns:
            Processed audio bytes
        """
        task_id = f"{session_id}_chunk_{int(time.time() * 1000)}"
        
        try:
            self._processing_stats["total_tasks"] += 1
            start_time = time.time()
            
            if processing_mode == "standard":
                # Standard mode: minimal processing, run directly
                processed_audio = audio_data
            else:
                # Enhanced/Playback mode: run in process pool for CPU-intensive work
                loop = asyncio.get_event_loop()
                processed_audio = await loop.run_in_executor(
                    self._process_pool,
                    self._sync_audio_processing,
                    audio_data,
                    processing_mode
                )
            
            # Update stats
            processing_time = time.time() - start_time
            self._processing_stats["completed_tasks"] += 1
            self._update_avg_processing_time(processing_time)
            
            return processed_audio
            
        except Exception as e:
            self._processing_stats["failed_tasks"] += 1
            logger.error(f"Audio processing failed for {task_id}: {e}")
            return audio_data  # Return original audio as fallback
        finally:
            # Clean up task reference
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
    
    async def transcribe_audio_async(
        self, 
        session_id: str, 
        audio_data: bytes, 
        is_final: bool = False
    ) -> str:
        """
        Transcribe audio asynchronously using thread pool
        
        Args:
            session_id: Unique session identifier
            audio_data: Audio bytes to transcribe
            is_final: Whether this is final transcription
            
        Returns:
            Transcribed text
        """
        task_id = f"{session_id}_transcribe_{int(time.time() * 1000)}"
        
        try:
            self._processing_stats["total_tasks"] += 1
            start_time = time.time()
            
            # Run transcription in thread pool (I/O-bound)
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(
                self._thread_pool,
                self._sync_transcription,
                audio_data,
                is_final
            )
            
            # Update stats
            processing_time = time.time() - start_time
            self._processing_stats["completed_tasks"] += 1
            self._update_avg_processing_time(processing_time)
            
            return transcript
            
        except Exception as e:
            self._processing_stats["failed_tasks"] += 1
            logger.error(f"Transcription failed for {task_id}: {e}")
            return ""
        finally:
            # Clean up task reference
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
    
    async def generate_soap_async(
        self, 
        session_id: str, 
        transcript: str
    ) -> Dict[str, Any]:
        """
        Generate SOAP note asynchronously using thread pool
        
        Args:
            session_id: Unique session identifier
            transcript: Complete transcript text
            
        Returns:
            SOAP note data with source mapping
        """
        task_id = f"{session_id}_soap_{int(time.time() * 1000)}"
        
        try:
            self._processing_stats["total_tasks"] += 1
            start_time = time.time()
            
            # Run SOAP generation in thread pool (I/O-bound AI API call)
            loop = asyncio.get_event_loop()
            soap_data = await loop.run_in_executor(
                self._thread_pool,
                self._sync_soap_generation,
                transcript
            )
            
            # Update stats
            processing_time = time.time() - start_time
            self._processing_stats["completed_tasks"] += 1
            self._update_avg_processing_time(processing_time)
            
            return soap_data
            
        except Exception as e:
            self._processing_stats["failed_tasks"] += 1
            logger.error(f"SOAP generation failed for {task_id}: {e}")
            return {
                "soap_note": f"Error generating SOAP note: {str(e)}",
                "soap_sections": {},
                "transcript_segments": []
            }
        finally:
            # Clean up task reference
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
    
    def _sync_audio_processing(self, audio_data: bytes, processing_mode: str) -> bytes:
        """Synchronous audio processing for executor"""
        try:
            import numpy as np
            import noisereduce as nr
            from scipy import signal
            
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            if len(audio_array) < 512:
                return audio_data
            
            if processing_mode == "enhanced":
                # Enhanced processing
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
                        logger.warning(f"Enhanced processing failed: {e}")
            
            # Convert back to int16
            final_audio = (audio_array * 32768.0).clip(-32768, 32767).astype(np.int16)
            return final_audio.tobytes()
            
        except Exception as e:
            logger.error(f"Sync audio processing failed: {e}")
            return audio_data
    
    def _sync_transcription(self, audio_data: bytes, is_final: bool) -> str:
        """Synchronous transcription for executor"""
        try:
            from services.transcription import TranscriptionService
            
            # Create service instance (thread-safe)
            transcription_service = TranscriptionService()
            
            if is_final:
                # Use asyncio.run for async method in thread
                import asyncio
                return asyncio.run(transcription_service.transcribe_complete_audio(audio_data))
            else:
                import asyncio
                return asyncio.run(transcription_service.transcribe_audio_chunk(audio_data))
                
        except Exception as e:
            logger.error(f"Sync transcription failed: {e}")
            return ""
    
    def _sync_soap_generation(self, transcript: str) -> Dict[str, Any]:
        """Synchronous SOAP generation for executor"""
        try:
            from services.soap_generator import SOAPGeneratorService
            
            # Create service instance (thread-safe)
            soap_generator = SOAPGeneratorService()
            
            # Use asyncio.run for async method in thread
            import asyncio
            return asyncio.run(soap_generator.generate_soap_note(transcript))
            
        except Exception as e:
            logger.error(f"Sync SOAP generation failed: {e}")
            return {
                "soap_note": f"Error generating SOAP note: {str(e)}",
                "soap_sections": {},
                "transcript_segments": []
            }
    
    def _update_avg_processing_time(self, processing_time: float):
        """Update average processing time"""
        completed = self._processing_stats["completed_tasks"]
        current_avg = self._processing_stats["avg_processing_time"]
        
        # Rolling average calculation
        if completed == 1:
            self._processing_stats["avg_processing_time"] = processing_time
        else:
            self._processing_stats["avg_processing_time"] = (
                (current_avg * (completed - 1) + processing_time) / completed
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing pool statistics"""
        return {
            **self._processing_stats,
            "queue_size": len(self._active_tasks),
            "thread_pool_workers": self._thread_pool._max_workers if self._thread_pool else 0,
            "process_pool_workers": self._process_pool._max_workers if self._process_pool else 0,
            "active_tasks": list(self._active_tasks.keys())
        }

# Global processing pool instance
processing_pool = AudioProcessingPool()

async def get_processing_pool() -> AudioProcessingPool:
    """Get processing pool instance"""
    return processing_pool