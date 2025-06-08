import json
import asyncio
import logging
import tempfile
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.processing_pool import AudioProcessingPool, get_processing_pool
from services.session_manager import SessionManager, get_session_manager
from services.deepgram_streaming import get_streaming_pool
from database.connection import get_database
from config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/api/transcribe/{session_id}")
async def websocket_transcribe(websocket: WebSocket, session_id: str):
    """Concurrent WebSocket endpoint with async audio processing"""
    await websocket.accept()
    
    # Get scalable services
    session_mgr = await get_session_manager()
    processing_pool = await get_processing_pool()
    
    # Check if session exists
    session = await session_mgr.get_session(session_id)
    if not session:
        await websocket.close(code=4000, reason="Session not found")
        return
    
    # Processing settings
    processing_mode = session.get("processing_mode", "standard")
    
    try:
        logger.info(f"🎤 Started concurrent recording for session {session_id} ({processing_mode})")
        
        # Send connection status
        await websocket.send_json({
            "type": "connection_status",
            "data": {"status": "connected", "message": "Concurrent transcription active"}
        })
        
        chunk_count = 0
        accumulated_audio = b""
        full_transcript = ""  # Track full transcript separately
        last_sent_length = 0  # Track what we've already sent
        
        # Handle incoming messages concurrently
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
                
                if message["type"] == "websocket.receive":
                    if "text" in message:
                        # Handle text messages (settings, control)
                        data = json.loads(message["text"])
                        
                        if data.get("type") == "processing_settings":
                            processing_mode = data.get("processing_mode", "standard")
                            await session_mgr.update_session(session_id, {"processing_mode": processing_mode})
                            logger.info(f"🔧 Processing mode updated to: {processing_mode}")
                            
                            await websocket.send_json({
                                "type": "processing_status",
                                "data": {
                                    "mode": processing_mode,
                                    "message": f"Audio processing: {processing_mode} mode"
                                }
                            })
                            continue
                            
                        elif data.get("type") == "stop_recording":
                            logger.info(f"🛑 Stop recording for session {session_id}")
                            break
                    
                    elif "bytes" in message:
                        audio_data = message["bytes"]
                        
                        # Process audio chunk asynchronously (non-blocking)
                        processed_audio = await processing_pool.process_audio_chunk_async(
                            session_id, audio_data, processing_mode
                        )
                        
                        accumulated_audio += processed_audio
                        chunk_count += 1
                        
                        # Update session with buffer info
                        await session_mgr.update_session(session_id, {
                            "chunk_count": chunk_count,
                            "audio_buffer_size": len(accumulated_audio)
                        })
                        
                        # Process transcription every configured interval (async)
                        if chunk_count % settings.transcription_interval_chunks == 0:
                            # Don't wait for transcription - run in background
                            # Initialize transcript state
                            transcript_state = {
                                "full_transcript": full_transcript,
                                "last_sent_length": last_sent_length
                            }
                            # Create a copy for this async task
                            task_transcript_state = {
                                "full_transcript": transcript_state["full_transcript"],
                                "last_sent_length": transcript_state["last_sent_length"]
                            }
                            asyncio.create_task(
                                _process_transcription_chunk(
                                    websocket, session_id, accumulated_audio, 
                                    processing_mode, processing_pool,
                                    task_transcript_state
                                )
                            )
                        
                        # Log progress
                        if chunk_count % 50 == 0:
                            duration = chunk_count * 0.064  # 64ms per chunk
                            logger.info(f"📡 Session {session_id} ({processing_mode}): {chunk_count} chunks, {duration:.1f}s")
                            
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                logger.error(f"❌ WebSocket error: {e}")
                break
        
        # Process final accumulated audio asynchronously
        await _process_final_audio(
            websocket, session_id, accumulated_audio, processing_mode,
            session_mgr, processing_pool
        )
        
        await websocket.close()
        
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"Error: {str(e)}"}
        })
        await websocket.close()

async def _process_transcription_chunk(
    websocket: WebSocket,
    session_id: str,
    audio_data: bytes,
    processing_mode: str,
    processing_pool: AudioProcessingPool,
    transcript_state: dict
):
    """Process transcription chunk asynchronously without blocking WebSocket"""
    try:
        
        # Transcribe chunk asynchronously
        transcript_chunk = await processing_pool.transcribe_audio_async(
            session_id, audio_data, is_final=False
        )
        
        if transcript_chunk.strip():
            # Add to full transcript
            if transcript_state["full_transcript"] and not transcript_state["full_transcript"].endswith(' '):
                transcript_state["full_transcript"] += " "
            transcript_state["full_transcript"] += transcript_chunk.strip()
            
            # Send only the new part
            new_text = transcript_state["full_transcript"][transcript_state["last_sent_length"]:].strip()
            if new_text:
                logger.info(f"🎤 New transcript chunk ({processing_mode}): '{new_text}'")
                
                # Send incremental update
                await websocket.send_json({
                    "type": "transcript_update",
                    "data": {
                        "text": new_text,  # Only new text
                        "is_final": False,
                        "full_transcript": transcript_state["full_transcript"],  # Complete transcript for context
                        "processing_mode": processing_mode
                    }
                })
                
                transcript_state["last_sent_length"] = len(transcript_state["full_transcript"])
            
    except Exception as e:
        logger.error(f"Error processing transcription chunk: {e}")

async def _process_final_audio(
    websocket: WebSocket,
    session_id: str,
    accumulated_audio: bytes,
    processing_mode: str,
    session_mgr: SessionManager,
    processing_pool: AudioProcessingPool
):
    """Process final accumulated audio and generate SOAP note asynchronously"""
    logger.info(f"📝 Processing final audio for session {session_id} in {processing_mode} mode")
    
    if not accumulated_audio:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "No audio received"}
        })
        return
    
    try:
        start_time = datetime.now()
        
        # Step 1: Get final transcript asynchronously
        final_transcript = await processing_pool.transcribe_audio_async(
            session_id, accumulated_audio, is_final=True
        )
        
        if not final_transcript.strip():
            await websocket.send_json({
                "type": "error",
                "data": {"message": "No speech detected in recording"}
            })
            return
        
        # Step 2: Generate SOAP note asynchronously (runs in parallel with session update)
        soap_task = asyncio.create_task(
            processing_pool.generate_soap_async(session_id, final_transcript)
        )
        
        # Step 3: Update session status immediately
        await session_mgr.update_session(session_id, {
            "status": "processing_soap",
            "transcript": final_transcript
        })
        
        # Step 4: Wait for SOAP generation to complete
        soap_data = await soap_task
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Step 5: Update session with final data
        session_update = {
            "status": "completed",
            "soap_note": soap_data.get("soap_note", ""),
            "soap_sections": soap_data.get("soap_sections", {}),
            "transcript_segments": soap_data.get("transcript_segments", []),
            "processing_time": processing_time,
            "audio_processing_mode": processing_mode,
            "is_active": False  # Mark as completed
        }
        
        await session_mgr.update_session(session_id, session_update)
        
        # Step 6: Update database
        db = await get_database()
        await db.recordings.update_one(
            {"session_id": session_id},
            {"$set": session_update}
        )
        
        # Step 7: Send final results
        await websocket.send_json({
            "type": "session_complete",
            "data": {
                "session_id": session_id,
                "transcript": final_transcript,
                "soap_note": soap_data.get("soap_note", ""),
                "soap_sections": soap_data.get("soap_sections", {}),
                "transcript_segments": soap_data.get("transcript_segments", []),
                "processing_time": processing_time,
                "processing_mode": processing_mode
            }
        })
        
        logger.info(f"✅ Session {session_id} completed in {processing_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error processing final audio: {e}")
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"Processing failed: {str(e)}"}
        })

@router.on_event("startup")
async def startup_processing_pool():
    """Start background processing pools"""
    processing_pool = await get_processing_pool()
    await processing_pool.start_pool()

@router.on_event("shutdown") 
async def shutdown_processing_pool():
    """Stop background processing pools"""
    processing_pool = await get_processing_pool()
    await processing_pool.stop_pool()

async def _handle_file_based_processing(websocket: WebSocket, session_id: str, session_mgr: SessionManager, processing_pool: AudioProcessingPool, processing_mode: str):
    """Handle file-based processing for Enhanced mode"""
    chunk_count = 0
    accumulated_audio = b""
    
    try:
        # Handle incoming messages
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
                
                if message["type"] == "websocket.receive":
                    if "text" in message:
                        # Handle control messages
                        data = json.loads(message["text"])
                        if data.get("type") == "stop_recording":
                            logger.info(f"🛑 Stop recording for session {session_id}")
                            break
                    
                    elif "bytes" in message:
                        audio_data = message["bytes"]
                        
                        # Process audio with enhanced mode
                        processed_audio = await processing_pool.process_audio_async(
                            session_id, audio_data, processing_mode
                        )
                        
                        accumulated_audio += processed_audio
                        chunk_count += 1
                        
                        # Process transcription every configured interval
                        if chunk_count % settings.transcription_interval_chunks == 0:
                            asyncio.create_task(
                                _process_transcription_chunk_enhanced(
                                    websocket, session_id, accumulated_audio, 
                                    processing_mode, processing_pool
                                )
                            )
                        
                        # Log progress
                        if chunk_count % 50 == 0:
                            duration = chunk_count * 0.064
                            logger.info(f"📡 Session {session_id} ({processing_mode}): {chunk_count} chunks, {duration:.1f}s")
                            
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                logger.info(f"🔌 WebSocket disconnected for session {session_id}")
                break
            except Exception as e:
                logger.error(f"❌ File-based processing error: {e}")
                break
        
        # Process final audio
        if accumulated_audio:
            final_transcript = await processing_pool.transcribe_audio_async(
                session_id, accumulated_audio, is_final=True
            )
            
            if final_transcript.strip():
                await _generate_final_soap(websocket, session_id, final_transcript, session_mgr, processing_mode)
            else:
                await websocket.send_json({
                    "type": "error", 
                    "data": {"message": "No speech detected in recording"}
                })
                
    except Exception as e:
        logger.error(f"File-based processing error: {e}")
        raise

async def _process_transcription_chunk_enhanced(websocket: WebSocket, session_id: str, audio_data: bytes, processing_mode: str, processing_pool: AudioProcessingPool):
    """Process transcription chunk for enhanced mode"""
    try:
        transcript_chunk = await processing_pool.transcribe_audio_async(
            session_id, audio_data, is_final=False
        )
        
        if transcript_chunk.strip():
            logger.info(f"🎤 Enhanced chunk ({processing_mode}): '{transcript_chunk}'")
            
            # Send update
            await websocket.send_json({
                "type": "transcript_update",
                "data": {
                    "text": transcript_chunk,
                    "is_final": False,
                    "processing_mode": processing_mode
                }
            })
            
    except Exception as e:
        logger.error(f"Error processing enhanced transcription chunk: {e}")

async def _generate_final_soap(websocket: WebSocket, session_id: str, transcript: str, session_mgr: SessionManager, processing_mode: str):
    """Generate final SOAP note and send results"""
    try:
        from services.soap_generator import SoapGenerator
        
        start_time = datetime.now()
        soap_generator = SoapGenerator()
        soap_data = await soap_generator.generate_soap_with_mapping(transcript)
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Update session
        session_update = {
            "status": "completed",
            "transcript": transcript,
            "soap_note": soap_data.get("soap_note", ""),
            "soap_sections": soap_data.get("soap_sections", {}),
            "transcript_segments": soap_data.get("transcript_segments", []),
            "processing_time": processing_time,
            "audio_processing_mode": processing_mode
        }
        
        await session_mgr.update_session(session_id, session_update)
        
        # Send final results
        await websocket.send_json({
            "type": "session_complete",
            "data": {
                "session_id": session_id,
                "transcript": transcript,
                "soap_note": soap_data.get("soap_note", ""),
                "soap_sections": soap_data.get("soap_sections", {}),
                "transcript_segments": soap_data.get("transcript_segments", []),
                "processing_time": processing_time,
                "processing_mode": processing_mode
            }
        })
        
        logger.info(f"📝 Generated SOAP note for session {session_id} in {processing_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error generating SOAP: {e}")
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"SOAP generation failed: {str(e)}"}
        })
