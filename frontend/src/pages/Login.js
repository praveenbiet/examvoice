import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  TextField,
  Button,
  Typography,
  Paper,
  CircularProgress,
} from '@mui/material';
import MicIcon from '@mui/icons-material/Mic';
import StopIcon from '@mui/icons-material/Stop';
import axios from 'axios';

function Login() {
  const [candidateId, setCandidateId] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  let mediaRecorder = null;
  let audioChunks = [];

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunks.push(event.data);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      setError('Error accessing microphone. Please ensure you have granted microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      setIsRecording(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!candidateId) {
      setError('Please enter your Candidate ID');
      return;
    }

    if (audioChunks.length === 0) {
      setError('Please record your voice sample');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const formData = new FormData();
      formData.append('candidate_id', candidateId);
      formData.append('voice_sample', new Blob(audioChunks, { type: 'audio/wav' }));

      const response = await axios.post('http://localhost:5000/start_exam', formData);
      
      if (response.data.status === 'success') {
        navigate('/verification');
      } else {
        setError('Failed to start exam. Please try again.');
      }
    } catch (err) {
      setError('An error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Paper elevation={3} sx={{ p: 4, maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h4" component="h1" gutterBottom align="center">
        Welcome to Voice-Based Exam
      </Typography>
      
      <Box component="form" onSubmit={handleSubmit} sx={{ mt: 3 }}>
        <TextField
          fullWidth
          label="Candidate ID"
          value={candidateId}
          onChange={(e) => setCandidateId(e.target.value)}
          margin="normal"
          required
        />

        <Box sx={{ mt: 2, mb: 3 }}>
          <Typography variant="subtitle1" gutterBottom>
            Record your voice for verification:
          </Typography>
          <Button
            variant="contained"
            color={isRecording ? 'secondary' : 'primary'}
            startIcon={isRecording ? <StopIcon /> : <MicIcon />}
            onClick={isRecording ? stopRecording : startRecording}
            sx={{ mr: 2 }}
          >
            {isRecording ? 'Stop Recording' : 'Start Recording'}
          </Button>
          {isRecording && (
            <Typography variant="body2" color="error">
              Recording...
            </Typography>
          )}
        </Box>

        {error && (
          <Typography color="error" sx={{ mb: 2 }}>
            {error}
          </Typography>
        )}

        <Button
          type="submit"
          variant="contained"
          color="primary"
          fullWidth
          disabled={isLoading}
          sx={{ mt: 2 }}
        >
          {isLoading ? <CircularProgress size={24} /> : 'Start Exam'}
        </Button>
      </Box>
    </Paper>
  );
}

export default Login; 