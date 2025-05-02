import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  CircularProgress,
  Alert,
} from '@mui/material';
import MicIcon from '@mui/icons-material/Mic';
import StopIcon from '@mui/icons-material/Stop';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import axios from 'axios';

function Exam() {
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState(null);
  const [isCompleted, setIsCompleted] = useState(false);
  const canvasRef = useRef(null);
  let mediaRecorder = null;
  let audioChunks = [];
  let audioContext = null;
  let analyser = null;
  let animationFrame = null;

  useEffect(() => {
    getNextQuestion();
    return () => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
      }
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
      }
    };
  }, []);

  const setupAudioVisualizer = (stream) => {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    
    const canvas = canvasRef.current;
    const canvasContext = canvas.getContext('2d');
    
    function draw() {
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      analyser.getByteFrequencyData(dataArray);
      
      canvasContext.fillStyle = 'rgb(200, 200, 200)';
      canvasContext.fillRect(0, 0, canvas.width, canvas.height);
      
      const barWidth = (canvas.width / bufferLength) * 2.5;
      let barHeight;
      let x = 0;
      
      for(let i = 0; i < bufferLength; i++) {
        barHeight = dataArray[i];
        
        canvasContext.fillStyle = 'rgb(' + (barHeight+100) + ',50,50)';
        canvasContext.fillRect(x, canvas.height-barHeight/2, barWidth, barHeight/2);
        
        x += barWidth + 1;
      }
      
      animationFrame = requestAnimationFrame(draw);
    }
    
    draw();
  };

  const getNextQuestion = async () => {
    setIsLoading(true);
    setError('');
    setFeedback(null);

    try {
      const response = await axios.get('http://localhost:5000/get_question');
      setCurrentQuestion(response.data);
    } catch (err) {
      setError('Failed to load question. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        await submitAnswer(audioBlob);
      };

      setupAudioVisualizer(stream);
      mediaRecorder.start();
      setIsRecording(true);
      setError('');
      setFeedback(null);
    } catch (err) {
      setError('Error accessing microphone. Please ensure you have granted microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      setIsRecording(false);
      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
      }
    }
  };

  const submitAnswer = async (audioBlob) => {
    setIsLoading(true);
    setError('');

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob);
      formData.append('question_id', currentQuestion.question_id);

      const response = await axios.post('http://localhost:5000/process_answer', formData);
      
      setFeedback({
        text: response.data.feedback,
        similarity: response.data.similarity_score,
      });

      if (response.data.is_completed) {
        setIsCompleted(true);
      }
    } catch (err) {
      setError('Failed to process answer. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  if (isCompleted) {
    return (
      <Paper elevation={3} sx={{ p: 4, maxWidth: 600, mx: 'auto', textAlign: 'center' }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Exam Completed!
        </Typography>
        <Typography variant="body1" paragraph>
          Thank you for participating in the exam.
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper elevation={3} sx={{ p: 4, maxWidth: 600, mx: 'auto' }}>
      {isLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
          <CircularProgress />
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {currentQuestion && (
        <>
          <Typography variant="h5" component="h2" gutterBottom>
            Question:
          </Typography>
          <Typography variant="body1" paragraph>
            {currentQuestion.question_text}
          </Typography>

          <Box sx={{ mt: 3 }}>
            <canvas
              ref={canvasRef}
              width="100%"
              height="50"
              style={{
                display: isRecording ? 'block' : 'none',
                backgroundColor: '#f8f9fa',
                marginBottom: '1rem',
              }}
            />

            <Button
              variant="contained"
              color={isRecording ? 'secondary' : 'primary'}
              startIcon={isRecording ? <StopIcon /> : <MicIcon />}
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isLoading}
              sx={{ mb: 2 }}
            >
              {isRecording ? 'Stop Recording' : 'Start Recording'}
            </Button>

            {isRecording && (
              <Typography variant="body2" color="error" sx={{ mb: 2 }}>
                Recording...
              </Typography>
            )}
          </Box>

          {feedback && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="h6" gutterBottom>
                Feedback:
              </Typography>
              <Typography variant="body1" paragraph>
                {feedback.text}
              </Typography>
              <Typography variant="body1" color="primary">
                Similarity Score: {(feedback.similarity * 100).toFixed(2)}%
              </Typography>

              {!isCompleted && (
                <Button
                  variant="contained"
                  color="primary"
                  startIcon={<SkipNextIcon />}
                  onClick={getNextQuestion}
                  sx={{ mt: 2 }}
                >
                  Next Question
                </Button>
              )}
            </Box>
          )}
        </>
      )}
    </Paper>
  );
}

export default Exam; 