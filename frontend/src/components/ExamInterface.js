import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

const ExamInterface = () => {
    const { examId } = useParams();
    const [currentQuestion, setCurrentQuestion] = useState(null);
    const [isRecording, setIsRecording] = useState(false);
    const [recordedResponses, setRecordedResponses] = useState([]);
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);
    const audioPlayerRef = useRef(null);

    // ... existing code ...

    const playResponse = async (questionIndex) => {
        try {
            const response = await axios.get(
                `http://localhost:5000/api/get_response_audio/${localStorage.getItem('candidateId')}/${examId}/${questionIndex}`,
                { responseType: 'blob' }
            );
            
            const audioUrl = URL.createObjectURL(response.data);
            if (audioPlayerRef.current) {
                audioPlayerRef.current.src = audioUrl;
                audioPlayerRef.current.play();
            }
        } catch (error) {
            console.error('Error playing response:', error);
        }
    };

    return (
        <div className="exam-interface">
            <h2>Exam Interface</h2>
            {currentQuestion && (
                <div className="question-container">
                    <h3>Question {currentQuestion.index + 1}</h3>
                    <p>{currentQuestion.text}</p>
                    
                    <div className="recording-controls">
                        <button 
                            onClick={isRecording ? stopRecording : startRecording}
                            className={isRecording ? 'stop-button' : 'record-button'}
                        >
                            {isRecording ? 'Stop Recording' : 'Start Recording'}
                        </button>
                    </div>

                    <div className="recorded-responses">
                        <h4>Your Responses:</h4>
                        {recordedResponses.map((response, index) => (
                            <div key={index} className="response-item">
                                <p>Response {index + 1}</p>
                                <button 
                                    onClick={() => playResponse(currentQuestion.index)}
                                    className="play-button"
                                >
                                    Play Response
                                </button>
                            </div>
                        ))}
                    </div>

                    <audio ref={audioPlayerRef} style={{ display: 'none' }} />
                </div>
            )}
        </div>
    );
};

export default ExamInterface; 