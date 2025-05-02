import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
import axios from 'axios';

function Verification() {
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [verificationStatus, setVerificationStatus] = useState('');
  const navigate = useNavigate();
  let mediaRecorder = null;
  let audioChunks = [];

  useEffect(() => {
    return () => {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
      }
    };
  }, []);

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
      setError('');
      setVerificationStatus('');
    } catch (err) {
      setError('Error accessing microphone. Please ensure you have granted microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
      setIsRecording(false);
      verifyIdentity();
    }
  };

  const verifyIdentity = async () => {
    setIsLoading(true);
    setError('');

    try {
      const formData = new FormData();
      formData.append('voice_sample', new Blob(audioChunks, { type: 'audio/wav' }));

      const response = await axios.post('http://localhost:5000/verify_identity', formData);
      
      if (response.data.status === 'success') {
        setVerificationStatus('success');
        setTimeout(() => {
          navigate('/exam');
        }, 2000);
      } else {
        setVerificationStatus('failure');
        setError('Verification failed. Please try again.');
      }
    } catch (err) {
      setVerificationStatus('failure');
      setError('An error occurred during verification. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Paper elevation={3} sx={{ p: 4, maxWidth: 600, mx: 'auto' }}>
      <Typography variant="h4" component="h1" gutterBottom align="center">
        Voice Verification
      </Typography>
      
      <Typography variant="body1" paragraph align="center">
        Please speak to verify your identity
      </Typography>

      <Box sx={{ mt: 3, textAlign: 'center' }}>
        <Button
          variant="contained"
          color={isRecording ? 'secondary' : 'primary'}
          startIcon={isRecording ? <StopIcon /> : <MicIcon />}
          onClick={isRecording ? stopRecording : startRecording}
          disabled={isLoading}
          sx={{ mb: 2 }}
        >
          {isRecording ? 'Stop Verification' : 'Start Verification'}
        </Button>

        {isRecording && (
          <Typography variant="body2" color="error" sx={{ mb: 2 }}>
            Recording...
          </Typography>
        )}

        {verificationStatus === 'success' && (
          <Alert severity="success" sx={{ mb: 2 }}>
            Identity verified successfully!
          </Alert>
        )}

        {verificationStatus === 'failure' && (
          <Alert severity="error" sx={{ mb: 2 }}>
            Verification failed. Please try again.
          </Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {isLoading && (
          <CircularProgress sx={{ mt: 2 }} />
        )}
      </Box>
    </Paper>
  );
}

export default Verification; 