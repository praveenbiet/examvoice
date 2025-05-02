import axios from 'axios';
import {
    START_SESSION,
    SUBMIT_ANSWER,
    GET_SESSION_RESULTS,
    EXTEND_SESSION_TIME,
    UPDATE_TIME_REMAINING,
    SET_CURRENT_SESSION,
    SESSION_ERROR,
    CLEAR_SESSION_ERRORS
} from '../types';

// Start exam session
export const startSession = (examId) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.post(`/api/exams/${examId}/start`, {}, config);
        dispatch({
            type: START_SESSION,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: SESSION_ERROR,
            payload: err.response?.data?.message || 'Error starting session'
        });
    }
};

// Submit answer
export const submitAnswer = (sessionId, questionId, audioFile) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const formData = new FormData();
        formData.append('audio', audioFile);
        formData.append('question_id', questionId);

        const config = {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'multipart/form-data'
            }
        };

        const res = await axios.post(`/api/sessions/${sessionId}/answers`, formData, config);
        dispatch({
            type: SUBMIT_ANSWER,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: SESSION_ERROR,
            payload: err.response?.data?.message || 'Error submitting answer'
        });
    }
};

// Get session results
export const getSessionResults = (sessionId) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.get(`/api/sessions/${sessionId}/results`, config);
        dispatch({
            type: GET_SESSION_RESULTS,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: SESSION_ERROR,
            payload: err.response?.data?.message || 'Error fetching results'
        });
    }
};

// Extend session time
export const extendSessionTime = (sessionId, additionalMinutes) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.post(
            `/api/sessions/${sessionId}/extend`,
            { additional_minutes: additionalMinutes },
            config
        );
        dispatch({
            type: EXTEND_SESSION_TIME,
            payload: res.data.total_extension
        });
    } catch (err) {
        dispatch({
            type: SESSION_ERROR,
            payload: err.response?.data?.message || 'Error extending session time'
        });
    }
};

// Update time remaining
export const updateTimeRemaining = (sessionId) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.get(`/api/sessions/${sessionId}/time`, config);
        dispatch({
            type: UPDATE_TIME_REMAINING,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: SESSION_ERROR,
            payload: err.response?.data?.message || 'Error updating time'
        });
    }
};

// Set current session
export const setCurrentSession = (session) => (dispatch) => {
    dispatch({
        type: SET_CURRENT_SESSION,
        payload: session
    });
};

// Clear session errors
export const clearSessionErrors = () => (dispatch) => {
    dispatch({ type: CLEAR_SESSION_ERRORS });
}; 