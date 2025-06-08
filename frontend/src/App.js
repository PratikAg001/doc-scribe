import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [currentSession, setCurrentSession] = useState(null);
  const [liveTranscript, setLiveTranscript] = useState('');
  const [finalTranscript, setFinalTranscript] = useState('');
  const [liveTranscriptChunks, setLiveTranscriptChunks] = useState([]); // Array of live chunks
  const [soapNote, setSoapNote] = useState('');
  const [soapSections, setSoapSections] = useState({});
  const [hoveredSource, setHoveredSource] = useState(null);
  const [transcriptSegments, setTranscriptSegments] = useState([]);
  const [speakerRoles, setSpeakerRoles] = useState({});
  const [processingTime, setProcessingTime] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [error, setError] = useState('');
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [audioLevel, setAudioLevel] = useState(0);

  // Feedback system states
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedStatements, setEditedStatements] = useState({});
  const [showFeedbackForm, setShowFeedbackForm] = useState(false);
  const [learningAnalytics, setLearningAnalytics] = useState(null);
  const [showSegmentedView, setShowSegmentedView] = useState(false);

  // Audio processing settings  
  const [processingMode, setProcessingMode] = useState('standard');
  const [audioProcessingMode, setAudioProcessingMode] = useState('standard'); // standard, enhanced

  const mediaRecorderRef = useRef(null);
  const websocketRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);

  useEffect(() => {
    fetchSessions();
    fetchLearningAnalytics();
    return () => {
      // Cleanup WebSocket on unmount
      if (websocketRef.current) {
        websocketRef.current.close();
      }
    };
  }, []);

  const fetchLearningAnalytics = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/learning-analytics`);
      setLearningAnalytics(response.data);
    } catch (error) {
      console.error('Error fetching analytics:', error);
    }
  };

  const fetchSessions = async () => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/sessions`);
      setSessions(response.data);
    } catch (error) {
      console.error('Error fetching sessions:', error);
    }
  };

  const resetRecordingState = () => {
    setLiveTranscript('');
    setFinalTranscript('');
    setLiveTranscriptChunks([]);
    setSoapNote('');
    setSoapSections({});
    setTranscriptSegments([]);
    setHoveredSource(null);
    setProcessingTime(null);
    setError('');
    setAudioLevel(0);
    console.log('🔄 Recording state reset');
  };

  const startRecording = async () => {
    try {
      // Reset all states first
      resetRecordingState();
      
      // Start a new session with processing mode
      const sessionResponse = await axios.post(`${BACKEND_URL}/api/start-session`, {
        processing_mode: audioProcessingMode
      });
      const sessionId = sessionResponse.data.session_id;
      setCurrentSession(sessionId);

      // Get user media
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
          channelCount: 1
        } 
      });

      // Set up WebSocket connection for real-time transcription
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${BACKEND_URL.replace(/^https?:\/\//, '')}/api/transcribe/${sessionId}`;
      
      websocketRef.current = new WebSocket(wsUrl);
      
      websocketRef.current.onopen = () => {
        setConnectionStatus('connected');
        console.log('WebSocket connected for real-time transcription');
        
        // Send processing preferences
        const processingSettings = {
          type: 'processing_settings',
          processing_mode: audioProcessingMode
        };
        websocketRef.current.send(JSON.stringify(processingSettings));
        setProcessingMode(audioProcessingMode);
      };
      
      websocketRef.current.onmessage = (event) => {
        console.log('WebSocket message received:', event.data);
        const data = JSON.parse(event.data);
        
        if (data.type === 'connection_status') {
          setConnectionStatus(data.data.status);
          console.log('Connection status:', data.data.message);
        } else if (data.type === 'processing_status') {
          console.log('Processing status:', data.data.message);
          setProcessingMode(data.data.mode);
        } else if (data.type === 'speech_status') {
          console.log('Speech status:', data.data.status);
        } else if (data.type === 'transcript_update') {
          console.log('Transcript update:', data.data);
          
          if (data.data.is_final) {
            // Final complete transcript
            setFinalTranscript(data.data.full_transcript || '');
            setLiveTranscript(''); // Clear interim text
          } else if (data.data.text.trim()) {
            // Incremental update - add new text only
            const timestamp = new Date().toLocaleTimeString();
            const newChunk = {
              text: data.data.text,
              timestamp: timestamp,
              id: Date.now()
            };
            
            setLiveTranscriptChunks(prev => [...prev, newChunk]);
            console.log('📝 Added incremental chunk:', newChunk.text);
            
            // Show interim text in live transcript
            setLiveTranscript(data.data.text || '');
          }
        } else if (data.type === 'session_complete') {
          setFinalTranscript(data.data.transcript || '');
          setSoapNote(data.data.soap_note || '');
          setSoapSections(data.data.soap_sections || {});
          setTranscriptSegments(data.data.transcript_segments || []);
          setProcessingTime(data.data.processing_time);
          setIsProcessing(false);
          setLiveTranscript(''); // Clear any remaining interim text
          fetchSessions(); // Refresh session list
        } else if (data.type === 'error') {
          setError(data.data.message);
          setIsProcessing(false);
          setIsRecording(false);
        }
      };
      
      websocketRef.current.onerror = (error) => {
        setError('WebSocket connection error');
        console.error('WebSocket error:', error);
        setConnectionStatus('error');
      };
      
      websocketRef.current.onclose = () => {
        setConnectionStatus('disconnected');
        console.log('WebSocket disconnected');
      };

      // Set up audio processing for WebSocket streaming
      audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      const source = audioContextRef.current.createMediaStreamSource(stream);
      
      // Create a script processor to capture audio data
      processorRef.current = audioContextRef.current.createScriptProcessor(4096, 1, 1);
      
      let silenceCount = 0;
      let audioLevelSum = 0;
      let chunkCount = 0;
      
      processorRef.current.onaudioprocess = (event) => {
        if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
          const inputBuffer = event.inputBuffer.getChannelData(0);
          
          // Calculate audio level for monitoring
          let sum = 0;
          for (let i = 0; i < inputBuffer.length; i++) {
            sum += Math.abs(inputBuffer[i]);
          }
          const audioLevel = sum / inputBuffer.length;
          audioLevelSum += audioLevel;
          chunkCount++;
          
          // Log audio level every 2 seconds
          if (chunkCount % 32 === 0) {
            const avgLevel = audioLevelSum / 32;
            setAudioLevel(avgLevel);
            console.log(`Audio level: ${(avgLevel * 100).toFixed(2)}% ${avgLevel > 0.01 ? '🎤 SPEAKING' : '🔇 SILENT'}`);
            audioLevelSum = 0;
          }
          
          // Check for silence
          if (audioLevel < 0.01) {
            silenceCount++;
          } else {
            silenceCount = 0;
          }
          
          // Convert Float32Array to Int16Array (required by Deepgram)
          const int16Array = new Int16Array(inputBuffer.length);
          for (let i = 0; i < inputBuffer.length; i++) {
            int16Array[i] = Math.max(-32768, Math.min(32767, inputBuffer[i] * 32768));
          }
          
          // Send audio data to WebSocket
          websocketRef.current.send(int16Array.buffer);
        }
      };
      
      source.connect(processorRef.current);
      processorRef.current.connect(audioContextRef.current.destination);

      setIsRecording(true);

    } catch (error) {
      setError('Error starting recording: ' + error.message);
      console.error('Error starting recording:', error);
    }
  };

  const stopRecording = async () => {
    try {
      setIsRecording(false);
      setIsProcessing(true);
      setConnectionStatus('processing');
      console.log('🛑 Stopping recording and processing...');
      
      // Stop audio processing
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      
      if (audioContextRef.current) {
        await audioContextRef.current.close();
        audioContextRef.current = null;
      }
      
      // Send stop signal to WebSocket
      if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
        websocketRef.current.send(JSON.stringify({ type: 'stop_recording' }));
      }

      // Note: Don't reset state here - wait for session_complete to show final results
      
    } catch (error) {
      console.error('Error stopping recording:', error);
      setError('Error stopping recording: ' + error.message);
      setIsProcessing(false);
      setIsRecording(false);
    }
  };

  const selectSession = async (sessionId) => {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/session/${sessionId}`);
      const session = response.data;
      
      setSelectedSession(session);
      setFinalTranscript(session.transcript || '');
      setSoapNote(session.soap_note || '');
      setSoapSections(session.soap_sections || {});
      setTranscriptSegments(session.transcript_segments || []);
      setSpeakerRoles(session.speaker_roles || {});
      setProcessingTime(session.processing_time);
      setLiveTranscript('');
      
    } catch (error) {
      setError('Error fetching session: ' + error.message);
      console.error('Error fetching session:', error);
    }
  };

  const formatSOAPNote = (soapText) => {
    if (!soapText) return '';
    
    // Split by main SOAP sections and format
    return soapText
      .split('\n')
      .map((line, index) => {
        if (line.match(/^(SUBJECTIVE|OBJECTIVE|ASSESSMENT|PLAN)/i)) {
          return <div key={index} className="font-bold text-blue-600 mt-4 mb-2 text-lg">{line}</div>;
        } else if (line.match(/^(Chief Complaint|History of Present Illness|Physical Examination|Treatment|Medications)/i)) {
          return <div key={index} className="font-semibold text-gray-700 mt-3 mb-1">{line}</div>;
        } else if (line.trim()) {
          return <div key={index} className="ml-4 mb-1 text-gray-600">{line}</div>;
        }
        return <br key={index} />;
      });
  };

  const handleEditStatement = (section, index, newText, editType = 'style_improvement') => {
    const key = `${section}-${index}`;
    setEditedStatements(prev => ({
      ...prev,
      [key]: {
        section,
        statement_index: index,
        original_text: soapSections[section][index].statement,
        edited_text: newText,
        edit_type: editType
      }
    }));
  };

  const submitFeedback = async (satisfaction, timeSaved, comments) => {
    try {
      const edits = Object.values(editedStatements);
      
      const feedbackData = {
        session_id: selectedSession?.session_id || currentSession,
        edits: edits,
        overall_satisfaction: satisfaction,
        time_saved_minutes: timeSaved,
        comments: comments
      };

      await axios.post(`${BACKEND_URL}/api/submit-feedback`, feedbackData);
      
      setShowFeedbackForm(false);
      setIsEditMode(false);
      setEditedStatements({});
      
      // Refresh analytics
      fetchLearningAnalytics();
      
      alert('Thank you! Your feedback helps improve the AI system.');
      
    } catch (error) {
      console.error('Error submitting feedback:', error);
      alert('Error submitting feedback. Please try again.');
    }
  };

  const InteractiveSOAPNote = ({ soapSections, transcriptSegments }) => {
    if (!soapSections || Object.keys(soapSections).length === 0) {
      return <div className="text-gray-700">{formatSOAPNote(soapNote)}</div>;
    }

    const handleStatementHover = (statement) => {
      if (!isEditMode) {
        // Find the actual transcript text for the source segments
        const sourceText = statement.source_segments
          .map(segmentNum => {
            if (transcriptSegments && transcriptSegments[segmentNum - 1]) {
              return transcriptSegments[segmentNum - 1];
            }
            return null;
          })
          .filter(Boolean)
          .join(' ... ');
        
        setHoveredSource({
          statement: statement.statement,
          source_text: sourceText,
          confidence: statement.confidence,
          source_segments: statement.source_segments
        });
      }
    };

    const handleStatementLeave = () => {
      if (!isEditMode) {
        setHoveredSource(null);
      }
    };

    const getConfidenceColor = (confidence) => {
      if (confidence >= 0.9) return 'border-l-green-500 bg-green-50';
      if (confidence >= 0.8) return 'border-l-blue-500 bg-blue-50';
      if (confidence >= 0.7) return 'border-l-yellow-500 bg-yellow-50';
      return 'border-l-red-500 bg-red-50';
    };

    const getConfidenceIcon = (confidence) => {
      if (confidence >= 0.9) return '🟢';
      if (confidence >= 0.8) return '🔵';
      if (confidence >= 0.7) return '🟡';
      return '🔴';
    };

    const EditableStatement = ({ statement, section, index }) => {
      const [isEditing, setIsEditing] = useState(false);
      const [editText, setEditText] = useState(statement.statement);
      const [editType, setEditType] = useState('style_improvement');

      const saveEdit = () => {
        if (editText !== statement.statement) {
          handleEditStatement(section, index, editText, editType);
        }
        setIsEditing(false);
      };

      return (
        <div className={`relative p-4 border-l-4 rounded-r-lg transition-all duration-200 ${getConfidenceColor(statement.confidence)} ${isEditMode ? 'hover:shadow-lg cursor-pointer' : 'cursor-help hover:shadow-md'}`}>
          <div className="flex items-start justify-between">
            <div className="flex-1">
              {isEditing ? (
                <div className="space-y-3">
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    className="w-full p-2 border border-gray-300 rounded resize-none"
                    rows="2"
                    autoFocus
                  />
                  <div className="flex items-center space-x-2">
                    <select 
                      value={editType} 
                      onChange={(e) => setEditType(e.target.value)}
                      className="text-xs border border-gray-300 rounded px-2 py-1"
                    >
                      <option value="factual_correction">Factual Correction</option>
                      <option value="style_improvement">Style Improvement</option>
                      <option value="addition">Missing Information</option>
                      <option value="deletion">Remove Unnecessary</option>
                    </select>
                    <button 
                      onClick={saveEdit}
                      className="text-xs bg-green-500 text-white px-3 py-1 rounded hover:bg-green-600"
                    >
                      Save
                    </button>
                    <button 
                      onClick={() => {setIsEditing(false); setEditText(statement.statement);}}
                      className="text-xs bg-gray-500 text-white px-3 py-1 rounded hover:bg-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div 
                  className="text-gray-800 font-medium mb-2"
                  onClick={() => isEditMode && setIsEditing(true)}
                  onMouseEnter={() => handleStatementHover(statement)}
                  onMouseLeave={handleStatementLeave}
                >
                  {editedStatements[`${section}-${index}`]?.edited_text || statement.statement}
                  {editedStatements[`${section}-${index}`] && (
                    <span className="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                      ✏️ Edited
                    </span>
                  )}
                  {isEditMode && (
                    <span className="ml-2 text-xs text-gray-500">
                      (Click to edit)
                    </span>
                  )}
                </div>
              )}
              
              {!isEditing && (
                <div className="flex items-center space-x-4 text-xs text-gray-600">
                  <span className="flex items-center">
                    {getConfidenceIcon(statement.confidence)}
                    <span className="ml-1">
                      Confidence: {(statement.confidence * 100).toFixed(0)}%
                    </span>
                  </span>
                  <span className="flex items-center">
                    📍 Sources: {statement.source_segments.join(', ')}
                  </span>
                </div>
              )}
            </div>
          </div>
          
          {!isEditMode && hoveredSource && hoveredSource.statement === statement.statement && (
            <div className="absolute z-20 mt-2 p-4 bg-white border-2 border-blue-300 rounded-lg shadow-xl max-w-md left-0 top-full">
              <div className="flex items-center mb-2">
                <span className="text-sm font-semibold text-gray-700">📋 Source Evidence:</span>
                <span className="ml-2 text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                  {(hoveredSource.confidence * 100).toFixed(0)}% confidence
                </span>
              </div>
              <div className="text-sm text-gray-700 italic mb-3 p-3 bg-gray-50 rounded border-l-3 border-blue-400">
                "{hoveredSource.source_text}"
              </div>
              <div className="text-xs text-blue-600 flex items-center">
                💡 Referenced segments: {hoveredSource.source_segments.join(', ')}
              </div>
            </div>
          )}
        </div>
      );
    };

    const renderSection = (sectionName, statements) => (
      <div key={sectionName} className="mb-8">
        <h3 className="font-bold text-blue-600 text-lg mb-4 flex items-center">
          {sectionName.toUpperCase()} ({sectionName.charAt(0).toUpperCase()})
          {!isEditMode && (
            <span className="ml-2 text-sm font-normal text-gray-500">
              Hover for sources
            </span>
          )}
          {isEditMode && (
            <span className="ml-2 text-sm font-normal text-green-600">
              Click to edit
            </span>
          )}
        </h3>
        <div className="space-y-3">
          {statements.map((statement, index) => (
            <EditableStatement 
              key={index}
              statement={statement}
              section={sectionName}
              index={index}
            />
          ))}
        </div>
      </div>
    );

    return (
      <div className="soap-note-interactive">
        {!isEditMode && (
          <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div className="flex items-center text-blue-800">
              <span className="text-lg mr-2">🔍</span>
              <span className="font-medium">Interactive SOAP Note with Source Mapping</span>
            </div>
            <p className="text-blue-700 text-sm mt-1">
              Hover over any statement to see the exact transcript segments that support it. 
              Color coding indicates confidence level of the AI's interpretation.
            </p>
          </div>
        )}

        {isEditMode && (
          <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
            <div className="flex items-center text-green-800">
              <span className="text-lg mr-2">✏️</span>
              <span className="font-medium">Edit Mode Active</span>
            </div>
            <p className="text-green-700 text-sm mt-1">
              Click any statement to edit it. Your changes help improve the AI system for future use.
            </p>
          </div>
        )}
        
        {Object.entries(soapSections).map(([sectionName, statements]) =>
          renderSection(sectionName, statements)
        )}
        
        {!isEditMode && (
          <div className="mt-6 p-3 bg-gray-50 border border-gray-200 rounded-lg">
            <div className="text-sm text-gray-600">
              <strong>Legend:</strong>
              <span className="ml-4">🟢 High confidence (90%+)</span>
              <span className="ml-4">🔵 Good confidence (80-89%)</span>
              <span className="ml-4">🟡 Moderate confidence (70-79%)</span>
              <span className="ml-4">🔴 Low confidence (&lt;70%)</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  const MedicalSpeakerDisplay = ({ transcriptSegments, speakerRoles }) => {
    if (!transcriptSegments || transcriptSegments.length === 0) {
      return null;
    }

    const getSpeakerColor = (role) => {
      const colors = {
        'doctor': 'text-blue-600 bg-blue-50 border-blue-200',
        'patient': 'text-green-600 bg-green-50 border-green-200', 
        'nurse': 'text-purple-600 bg-purple-50 border-purple-200',
        'unknown': 'text-gray-600 bg-gray-50 border-gray-200'
      };
      return colors[role] || colors.unknown;
    };
    
    const getSpeakerIcon = (role) => {
      const icons = {
        'doctor': '👨‍⚕️',
        'patient': '🙋‍♂️',
        'nurse': '👩‍⚕️',
        'unknown': '❓'
      };
      return icons[role] || icons.unknown;
    };
    
    return (
      <div className="medical-conversation space-y-3">
        <h4 className="font-semibold text-gray-700 mb-3">Speaker-Identified Conversation</h4>
        {transcriptSegments.map((segment, index) => {
          const role = segment.role || speakerRoles[segment.speaker] || 'unknown';
          return (
            <div key={index} className={`conversation-segment p-3 rounded-lg border ${getSpeakerColor(role)}`}>
              <div className="speaker-header flex items-center mb-2">
                <span className="speaker-icon mr-2 text-lg">{getSpeakerIcon(role)}</span>
                <span className="speaker-label font-semibold">
                  {role ? role.charAt(0).toUpperCase() + role.slice(1) : `Speaker ${segment.speaker}`}
                </span>
                <span className="timestamp text-xs text-gray-500 ml-auto">
                  {segment.timestamp ? new Date(segment.timestamp * 1000).toLocaleTimeString() : ''}
                </span>
              </div>
              <div className="segment-text text-gray-700">{segment.text}</div>
            </div>
          );
        })}
      </div>
    );
  };

  const CleanTranscript = ({ transcript, transcriptSegments, hoveredSource }) => {
    const scrollableRef = useRef(null);
    
    if (!transcript) {
      return <p className="text-gray-500 italic">No transcript available</p>;
    }

    // If no source mapping, just show clean transcript
    if (!transcriptSegments || transcriptSegments.length === 0 || !hoveredSource) {
      return (
        <div ref={scrollableRef} className="text-gray-700 whitespace-pre-wrap leading-relaxed">
          {transcript}
        </div>
      );
    }

    // Create highlighted transcript with source mapping
    let highlightedText = transcript;
    const sourceSegments = hoveredSource.source_segments || [];
    
    // Build highlighted text by finding segment text within the clean transcript
    sourceSegments.forEach(segmentNum => {
      if (transcriptSegments[segmentNum - 1]) {
        const segmentText = transcriptSegments[segmentNum - 1];
        const escapedText = segmentText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        highlightedText = highlightedText.replace(
          new RegExp(`(${escapedText})`, 'gi'),
          '<mark class="bg-yellow-200 px-1 rounded font-medium">$1</mark>'
        );
      }
    });

    // Auto-scroll to highlighted text
    useEffect(() => {
      if (hoveredSource && scrollableRef.current) {
        const highlighted = scrollableRef.current.querySelector('mark');
        if (highlighted) {
          highlighted.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
          });
        }
      }
    }, [hoveredSource]);

    return (
      <div 
        ref={scrollableRef}
        className="text-gray-700 whitespace-pre-wrap leading-relaxed"
        dangerouslySetInnerHTML={{ __html: highlightedText }}
      />
    );
  };

  const SegmentedTranscript = ({ transcriptSegments, hoveredSource }) => {
    if (!transcriptSegments || transcriptSegments.length === 0) {
      return <p className="text-gray-500 italic">No segments available for source mapping</p>;
    }

    return (
      <div className="space-y-2">
        <div className="text-sm text-blue-600 mb-3">
          📍 Source Mapping View - Hover over SOAP statements to see highlighted segments
        </div>
        {transcriptSegments.map((segment, index) => {
          const segmentNumber = index + 1;
          const isHighlighted = hoveredSource?.source_segments?.includes(segmentNumber);
          
          return (
            <div
              key={index}
              className={`p-3 rounded-lg transition-all duration-200 ${
                isHighlighted 
                  ? 'bg-yellow-200 border-2 border-yellow-400 shadow-md transform scale-[1.02]' 
                  : 'bg-gray-50 border border-gray-200 hover:bg-gray-100'
              }`}
            >
              <div className="flex items-start space-x-3">
                <span className={`text-xs font-bold px-2 py-1 rounded ${
                  isHighlighted 
                    ? 'bg-yellow-500 text-white' 
                    : 'bg-gray-300 text-gray-600'
                }`}>
                  [{segmentNumber}]
                </span>
                <span className={`text-sm flex-1 ${
                  isHighlighted ? 'text-gray-900 font-medium' : 'text-gray-700'
                }`}>
                  {segment}
                </span>
                {isHighlighted && (
                  <span className="text-yellow-600 text-lg">📍</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const FeedbackForm = () => {
    const [satisfaction, setSatisfaction] = useState(4);
    const [timeSaved, setTimeSaved] = useState(5);
    const [comments, setComments] = useState('');

    const handleSubmit = (e) => {
      e.preventDefault();
      submitFeedback(satisfaction, timeSaved, comments);
    };

    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            📝 Feedback on SOAP Note Quality
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Overall Satisfaction (1-5 scale)
              </label>
              <input
                type="range"
                min="1"
                max="5"
                value={satisfaction}
                onChange={(e) => setSatisfaction(Number(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-gray-500">
                <span>Poor</span>
                <span className="font-medium">Rating: {satisfaction}/5</span>
                <span>Excellent</span>
              </div>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Time Saved (minutes)
              </label>
              <input
                type="number"
                value={timeSaved}
                onChange={(e) => setTimeSaved(Number(e.target.value))}
                className="w-full border border-gray-300 rounded px-3 py-2"
                min="0"
                max="60"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Additional Comments (Optional)
              </label>
              <textarea
                value={comments}
                onChange={(e) => setComments(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2"
                rows="3"
                placeholder="Any specific improvements or issues..."
              />
            </div>
            
            <div className="flex space-x-3">
              <button
                type="submit"
                className="flex-1 bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
              >
                Submit Feedback
              </button>
              <button
                type="button"
                onClick={() => setShowFeedbackForm(false)}
                className="flex-1 bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-600"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  };

  // const LearningAnalytics = () => {
  //   if (!learningAnalytics) return null;

  //   return (
  //     <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
  //       <h3 className="text-xl font-semibold text-gray-800 mb-4 flex items-center">
  //         📊 AI Learning Progress
  //         <span className="ml-2 text-sm font-normal text-green-600">
  //           System improving with your feedback
  //         </span>
  //       </h3>
        
  //       <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
  //         <div className="bg-blue-50 p-4 rounded-lg">
  //           <div className="text-2xl font-bold text-blue-600">
  //             {learningAnalytics.total_sessions_with_feedback}
  //           </div>
  //           <div className="text-sm text-gray-600">Sessions with Feedback</div>
  //         </div>
          
  //         <div className="bg-green-50 p-4 rounded-lg">
  //           <div className="text-2xl font-bold text-green-600">
  //             {learningAnalytics.average_satisfaction}/5
  //           </div>
  //           <div className="text-sm text-gray-600">Average Satisfaction</div>
  //         </div>
          
  //         <div className="bg-purple-50 p-4 rounded-lg">
  //           <div className="text-2xl font-bold text-purple-600">
  //             {learningAnalytics.total_time_saved_minutes}m
  //           </div>
  //           <div className="text-sm text-gray-600">Total Time Saved</div>
  //         </div>
  //       </div>
        
  //       <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
  //         <div>
  //           <h4 className="font-medium text-gray-700 mb-2">Common Improvements</h4>
  //           <div className="space-y-1">
  //             {Object.entries(learningAnalytics.common_edit_types).map(([type, count]) => (
  //               <div key={type} className="flex justify-between text-sm">
  //                 <span className="capitalize">{type.replace('_', ' ')}</span>
  //                 <span className="text-gray-500">{count}</span>
  //               </div>
  //             ))}
  //           </div>
  //         </div>
          
  //         <div>
  //           <h4 className="font-medium text-gray-700 mb-2">Learning Trends</h4>
  //           <div className="space-y-1 text-sm">
  //             <div className="flex items-center">
  //               <span className="text-green-500 mr-2">📈</span>
  //               <span>Accuracy: {learningAnalytics.improvement_trends.accuracy_trend}</span>
  //             </div>
  //             <div className="flex items-center">
  //               <span className="text-blue-500 mr-2">📉</span>
  //               <span>Edit frequency: {learningAnalytics.improvement_trends.edit_frequency}</span>
  //             </div>
  //             <div className="flex items-center">
  //               <span className="text-purple-500 mr-2">🎯</span>
  //               <span>Confidence: {learningAnalytics.improvement_trends.confidence_calibration}</span>
  //             </div>
  //           </div>
  //         </div>
  //       </div>
  //     </div>
  //   );
  // };

  const displayTranscript = finalTranscript + (liveTranscript ? ` ${liveTranscript}` : '');

  const LiveTranscriptDisplay = () => {
    return (
      <div className="space-y-2">
        {/* Live transcript chunks */}
        {liveTranscriptChunks.map((chunk) => (
          <div key={chunk.id} className="flex items-start space-x-3 p-2 bg-blue-50 rounded-lg">
            <span className="text-xs text-blue-600 font-mono min-w-fit">
              {chunk.timestamp}
            </span>
            <span className="text-gray-800 flex-1">
              {chunk.text}
            </span>
            <span className="text-blue-500 text-sm">✓</span>
          </div>
        ))}
        
        {/* Current interim text */}
        {liveTranscript && (
          <div className="flex items-start space-x-3 p-2 bg-yellow-50 rounded-lg border-l-3 border-yellow-400">
            <span className="text-xs text-yellow-600 font-mono min-w-fit">
              {new Date().toLocaleTimeString()}
            </span>
            <span className="text-gray-700 flex-1 italic">
              {liveTranscript}
            </span>
            <span className="text-yellow-500 text-sm animate-pulse">⏳</span>
          </div>
        )}
        
        {/* Recording indicator */}
        {isRecording && !liveTranscript && liveTranscriptChunks.length === 0 && (
          <div className="flex items-center justify-center p-4 text-gray-500">
            <div className="animate-pulse flex items-center space-x-2">
              <div className="w-2 h-2 bg-red-500 rounded-full animate-ping"></div>
              <span>Listening for speech...</span>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">
            AI Medical Scribe System
          </h1>
          <p className="text-gray-600 text-lg">
            Real-time transcription with AI-powered SOAP note generation
          </p>
          {connectionStatus === 'connected' && (
            <div className="mt-2 text-green-600 text-sm font-medium">
              🟢 Real-time transcription active
              {isRecording && (
                <div className="mt-1 flex items-center space-x-2">
                  <span>Audio level:</span>
                  <div className="w-32 h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-200 ${
                        audioLevel > 0.02 ? 'bg-green-500' : 
                        audioLevel > 0.01 ? 'bg-yellow-500' : 
                        'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(100, audioLevel * 5000)}%` }}
                    ></div>
                  </div>
                  <span className="text-xs">
                    {audioLevel > 0.02 ? '🎤 Speaking' : audioLevel > 0.01 ? '🔊 Detected' : '🔇 Silent'}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        {/* Recording Controls */}
        <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
          <h2 className="text-2xl font-semibold text-gray-800 mb-4">Record New Session</h2>
          
          {/* Audio Processing Settings */}
          <div className="mb-6 p-4 bg-gray-50 rounded-lg border">
            <h3 className="text-lg font-medium text-gray-700 mb-3">🎤 Audio Processing Settings</h3>
            
            <div className="space-y-4">
              {/* Processing Mode Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Processing Mode</label>
                <div className="space-y-2">
                  <label className="flex items-center cursor-pointer">
                    <input
                      type="radio"
                      value="standard"
                      checked={audioProcessingMode === 'standard'}
                      onChange={(e) => setAudioProcessingMode(e.target.value)}
                      disabled={isRecording || isProcessing}
                      className="w-4 h-4 text-green-600 bg-gray-100 border-gray-300 focus:ring-green-500"
                    />
                    <span className="ml-2 text-sm">
                      <span className="font-medium text-green-700">🟢 Standard Mode</span>
                      <span className="text-gray-600 ml-2">- Fast processing for live conversations (quiet environments)</span>
                    </span>
                  </label>
                  
                  <label className="flex items-center cursor-pointer">
                    <input
                      type="radio"
                      value="enhanced"
                      checked={audioProcessingMode === 'enhanced'}
                      onChange={(e) => setAudioProcessingMode(e.target.value)}
                      disabled={isRecording || isProcessing}
                      className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 focus:ring-blue-500"
                    />
                    <span className="ml-2 text-sm">
                      <span className="font-medium text-blue-700">🔵 Enhanced Mode</span>
                      <span className="text-gray-600 ml-2">- Advanced noise reduction for noisy environments (+300ms)</span>
                    </span>
                  </label>
                </div>
              </div>
              
              {/* Mode Description */}
              <div className="p-3 rounded-lg border-l-4 bg-white border-l-gray-400">
                <div className="flex items-center space-x-2 mb-2">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    audioProcessingMode === 'standard' ? 'bg-green-100 text-green-800' :
                    'bg-blue-100 text-blue-800'
                  }`}>
                    {audioProcessingMode === 'standard' ? '🟢 Standard Mode Active' :
                     '🔵 Enhanced Mode Active'}
                  </span>
                  {audioProcessingMode !== 'standard' && (
                    <span className="text-amber-600 text-xs">
                      ⚠️ +300-500ms processing time
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-600">
                  {audioProcessingMode === 'standard' && 
                    'Real-time streaming with minimal latency. Best for quiet exam rooms and live conversations.'
                  }
                  {audioProcessingMode === 'enhanced' && 
                    'Advanced noise reduction with spectral gating and professional audio effects. Best for busy hospitals and challenging environments.'
                  }
                </div>
              </div>
            </div>
          </div>
          
          <div className="flex items-center justify-center space-x-4">
            {!isRecording && !isProcessing ? (
              <button
                onClick={startRecording}
                className="bg-green-500 hover:bg-green-600 text-white font-bold py-4 px-8 rounded-full flex items-center space-x-2 transition-colors"
              >
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
                </svg>
                <span>Start Real-time Recording</span>
              </button>
            ) : isRecording ? (
              <div className="text-center">
                <button
                  onClick={stopRecording}
                  className="bg-red-500 hover:bg-red-600 text-white font-bold py-4 px-8 rounded-full flex items-center space-x-2 transition-colors animate-pulse"
                >
                  <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clipRule="evenodd" />
                  </svg>
                  <span>Stop Recording & Generate SOAP</span>
                </button>
                {processingMode && (
                  <div className="mt-2 text-sm text-gray-600">
                    Processing Mode: <span className="font-medium capitalize">{processingMode}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center space-x-2 text-blue-600">
                <svg className="animate-spin w-6 h-6" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span className="font-semibold">Generating SOAP note...</span>
              </div>
            )}
          </div>

          {processingTime && (
            <div className="mt-4 text-center text-sm text-gray-600">
              SOAP note generated in {processingTime.toFixed(2)} seconds
            </div>
          )}
        </div>

        {/* Live Transcription Display */}
        {(displayTranscript || isRecording || liveTranscriptChunks.length > 0) && (
          <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold text-gray-800">
                {isRecording ? 'Live Transcription' : 'Transcript'}
                {transcriptSegments.length > 0 && (
                  <span className="text-sm font-normal text-blue-600 ml-2">
                    (Enhanced with Source Mapping)
                  </span>
                )}
              </h3>
              
              {/* Clear/Reset button */}
              {!isRecording && (liveTranscriptChunks.length > 0 || finalTranscript) && (
                <button
                  onClick={resetRecordingState}
                  className="text-sm bg-gray-200 hover:bg-gray-300 text-gray-700 px-3 py-1 rounded-full transition-colors flex items-center space-x-1"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>Clear</span>
                </button>
              )}
            </div>
            <div className="bg-gray-50 p-4 rounded-lg max-h-64 overflow-y-auto">
              {isRecording ? (
                <LiveTranscriptDisplay />
              ) : (
                <p className="text-gray-700 whitespace-pre-wrap">
                  {displayTranscript}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Results Display */}
        {(finalTranscript || soapNote) && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Final Transcript */}
            <div className="bg-white rounded-lg shadow-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-semibold text-gray-800">Final Transcript</h3>
                {transcriptSegments.length > 0 && (
                  <div className="flex items-center space-x-2">
                    <label className="flex items-center text-sm">
                      <input
                        type="checkbox"
                        checked={showSegmentedView}
                        onChange={(e) => setShowSegmentedView(e.target.checked)}
                        className="mr-2"
                      />
                      Source Mapping View
                    </label>
                  </div>
                )}
              </div>
              <div className="bg-gray-50 p-4 rounded-lg max-h-96 overflow-y-auto custom-scrollbar">
                {showSegmentedView && transcriptSegments.length > 0 ? (
                  <SegmentedTranscript 
                    transcriptSegments={transcriptSegments}
                    hoveredSource={hoveredSource}
                  />
                ) : (
                  <CleanTranscript 
                    transcript={finalTranscript}
                    transcriptSegments={transcriptSegments}
                    hoveredSource={hoveredSource}
                  />
                )}
              </div>
            </div>

            {/* SOAP Note */}
            <div className="bg-white rounded-lg shadow-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-semibold text-gray-800">
                  Interactive SOAP Note
                  {Object.keys(soapSections).length > 0 && (
                    <span className="text-sm font-normal text-blue-600 ml-2">
                      {isEditMode ? '(Edit Mode)' : '(Hover for sources)'}
                    </span>
                  )}
                </h3>
                
                {Object.keys(soapSections).length > 0 && (
                  <div className="flex space-x-2">
                    {!isEditMode ? (
                      <button
                        onClick={() => setIsEditMode(true)}
                        className="bg-green-500 text-white px-4 py-2 rounded text-sm hover:bg-green-600 flex items-center"
                      >
                        ✏️ Edit & Improve
                      </button>
                    ) : (
                      <div className="flex space-x-2">
                        <button
                          onClick={() => setShowFeedbackForm(true)}
                          className="bg-blue-500 text-white px-4 py-2 rounded text-sm hover:bg-blue-600"
                          disabled={Object.keys(editedStatements).length === 0}
                        >
                          💾 Submit Feedback ({Object.keys(editedStatements).length} edits)
                        </button>
                        <button
                          onClick={() => {
                            setIsEditMode(false);
                            setEditedStatements({});
                          }}
                          className="bg-gray-500 text-white px-4 py-2 rounded text-sm hover:bg-gray-600"
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="bg-gray-50 p-4 rounded-lg max-h-96 overflow-y-auto custom-scrollbar">
                <InteractiveSOAPNote 
                  soapSections={soapSections}
                  transcriptSegments={transcriptSegments}
                />
              </div>
            </div>
          </div>
        )}

        {/* Learning Analytics */}
        {/* <LearningAnalytics /> */}

        {/* Session History */}
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h3 className="text-xl font-semibold text-gray-800 mb-4">Session History</h3>
          
          {sessions.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No sessions recorded yet</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Session ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created At
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Processing Time
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {sessions.map((session) => (
                    <tr key={session.session_id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {session.session_id.substring(0, 8)}...
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(session.created_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          session.status === 'completed' ? 'bg-green-100 text-green-800' :
                          session.status === 'processing' ? 'bg-yellow-100 text-yellow-800' :
                          session.status === 'error' ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {session.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {session.processing_time ? `${session.processing_time.toFixed(2)}s` : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {session.status === 'completed' && (
                          <button
                            onClick={() => selectSession(session.session_id)}
                            className="text-blue-600 hover:text-blue-900 font-medium"
                          >
                            View Details
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        
        {/* Feedback Form Modal */}
        {showFeedbackForm && <FeedbackForm />}
      </div>
    </div>
  );
}

export default App;
