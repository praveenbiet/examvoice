import axios from 'axios';
import { io } from 'socket.io-client';

// Create axios instance with base URL
const api = axios.create({
    baseURL: process.env.REACT_APP_API_URL || 'http://localhost:5000/api',
    headers: {
        'Content-Type': 'application/json'
    }
});

// Create socket instance
const socket = io(process.env.REACT_APP_WS_URL || 'ws://localhost:5000', {
    autoConnect: false,
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: 5
});

// Add request interceptor for logging
api.interceptors.request.use(
    config => {
        console.log('Request:', config.method.toUpperCase(), config.url, config.data);
        return config;
    },
    error => {
        console.error('Request error:', error);
        return Promise.reject(error);
    }
);

// Add response interceptor for logging
api.interceptors.response.use(
    response => {
        console.log('Response:', response.status, response.data);
        return response;
    },
    error => {
        console.error('Response error:', error.response?.data || error.message);
        return Promise.reject(error);
    }
);

// Add token to requests
export const setAuthToken = (token) => {
    if (token) {
        api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
        delete api.defaults.headers.common['Authorization'];
    }
};

// Handle file upload
export const uploadFile = async (file, endpoint, token) => {
    const formData = new FormData();
    formData.append('file', file);

    const config = {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
        }
    };

    return await api.post(endpoint, formData, config);
};

// Handle API errors
export const handleApiError = (error) => {
    if (error.response) {
        // The request was made and the server responded with a status code
        // that falls out of the range of 2xx
        return {
            message: error.response.data.message || 'An error occurred',
            status: error.response.status,
            data: error.response.data
        };
    } else if (error.request) {
        // The request was made but no response was received
        return {
            message: 'No response from server',
            status: 0
        };
    } else {
        // Something happened in setting up the request that triggered an Error
        return {
            message: error.message || 'An error occurred',
            status: 0
        };
    }
};

// Format time remaining
export const formatTimeRemaining = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;

    return {
        hours,
        minutes,
        seconds: remainingSeconds,
        formatted: `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
    };
};

// Validate exam data
export const validateExamData = (examData) => {
    const errors = {};

    if (!examData.title) {
        errors.title = 'Title is required';
    }
    if (!examData.description) {
        errors.description = 'Description is required';
    }
    if (!examData.duration) {
        errors.duration = 'Duration is required';
    }
    if (examData.questions && examData.questions.length === 0) {
        errors.questions = 'At least one question is required';
    }

    return {
        isValid: Object.keys(errors).length === 0,
        errors
    };
};

// Format exam results
export const formatExamResults = (results) => {
    return {
        totalQuestions: results.length,
        correctAnswers: results.filter(r => r.is_correct).length,
        score: (results.filter(r => r.is_correct).length / results.length) * 100,
        details: results.map(r => ({
            question: r.question,
            answer: r.answer,
            isCorrect: r.is_correct,
            feedback: r.feedback
        }))
    };
};

// Create authenticated API call wrapper
export const createAuthenticatedCall = async (dispatch, action, apiCall, errorType) => {
    try {
        const res = await apiCall();
        dispatch({
            type: action,
            payload: res.data
        });
        return res.data;
    } catch (err) {
        const error = handleApiError(err);
        dispatch({
            type: errorType,
            payload: error.message
        });
        throw error;
    }
};

// Create authenticated API call with token
export const createAuthenticatedCallWithToken = async (dispatch, getState, action, apiCall, errorType) => {
    const token = getState().auth.token;
    setAuthToken(token);
    return createAuthenticatedCall(dispatch, action, apiCall, errorType);
};

// Create paginated API call
export const createPaginatedCall = async (dispatch, getState, action, apiCall, errorType, page = 1, limit = 10) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        action,
        () => apiCall(page, limit),
        errorType
    );
};

// Handle file upload with progress
export const uploadFileWithProgress = async (file, endpoint, token, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);

    const config = {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(percentCompleted);
        }
    };

    return await api.post(endpoint, formData, config);
};

// Create batch API call
export const createBatchCall = async (dispatch, getState, action, apiCalls, errorType) => {
    const token = getState().auth.token;
    setAuthToken(token);

    try {
        const results = await Promise.all(apiCalls.map(call => call()));
        const combinedData = results.map(res => res.data);
        
        dispatch({
            type: action,
            payload: combinedData
        });
        
        return combinedData;
    } catch (err) {
        const error = handleApiError(err);
        dispatch({
            type: errorType,
            payload: error.message
        });
        throw error;
    }
};

// Socket event handlers
export const setupSocket = (onConnect, onDisconnect, onError) => {
    socket.on('connect', () => {
        console.log('Connected to WebSocket server');
        onConnect?.();
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from WebSocket server');
        onDisconnect?.();
    });

    socket.on('error', (error) => {
        console.error('WebSocket error:', error);
        onError?.(error);
    });

    return socket;
};

// Join exam session
export const joinExamSession = (sessionId, onTimeUpdate) => {
    socket.emit('join_session', { session_id: sessionId });
    socket.on('time_update', (data) => {
        if (data.session_id === sessionId) {
            onTimeUpdate?.(data.time_remaining);
        }
    });
};

// Leave exam session
export const leaveExamSession = (sessionId) => {
    socket.emit('leave_session', { session_id: sessionId });
    socket.off('time_update');
};

export default api; 