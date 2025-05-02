import axios from 'axios';

// Create axios instance with base URL
const api = axios.create({
    baseURL: process.env.REACT_APP_API_URL || 'http://localhost:5000/api',
    headers: {
        'Content-Type': 'application/json'
    }
});

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

export default api; 