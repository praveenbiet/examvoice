import api, { createAuthenticatedCallWithToken } from '../../utils/api';
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
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        START_SESSION,
        () => api.post(`/exams/${examId}/start`, {}),
        SESSION_ERROR
    );
};

// Submit answer
export const submitAnswer = (sessionId, answerData) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        SUBMIT_ANSWER,
        () => api.post(`/sessions/${sessionId}/answer`, answerData),
        SESSION_ERROR
    );
};

// Get session results
export const getSessionResults = (sessionId) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        GET_SESSION_RESULTS,
        () => api.get(`/sessions/${sessionId}/results`),
        SESSION_ERROR
    );
};

// Extend session time
export const extendSessionTime = (sessionId, minutes) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        EXTEND_SESSION_TIME,
        () => api.post(`/sessions/${sessionId}/extend`, { minutes }),
        SESSION_ERROR
    );
};

// Update time remaining
export const updateTimeRemaining = (seconds) => (dispatch) => {
    dispatch({
        type: UPDATE_TIME_REMAINING,
        payload: seconds
    });
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