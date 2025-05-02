import api, { createAuthenticatedCallWithToken, createPaginatedCall } from '../../utils/api';
import {
    GET_EXAMS,
    GET_EXAM,
    GET_SCHEDULED_EXAMS,
    CREATE_EXAM,
    UPDATE_EXAM,
    DELETE_EXAM,
    TOGGLE_EXAM_STATUS,
    EXAM_ERROR,
    CLEAR_EXAM_ERRORS,
    SET_CURRENT_EXAM
} from '../types';

// Get all exams with pagination
export const getExams = (page = 1, limit = 10) => async (dispatch, getState) => {
    return createPaginatedCall(
        dispatch,
        getState,
        GET_EXAMS,
        (page, limit) => api.get(`/exams?page=${page}&limit=${limit}`),
        EXAM_ERROR,
        page,
        limit
    );
};

// Get single exam
export const getExam = (examId) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        GET_EXAM,
        () => api.get(`/exams/${examId}`),
        EXAM_ERROR
    );
};

// Get scheduled exams
export const getScheduledExams = () => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        GET_SCHEDULED_EXAMS,
        () => api.get('/exams/scheduled'),
        EXAM_ERROR
    );
};

// Create exam
export const createExam = (examData) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        CREATE_EXAM,
        () => api.post('/exams', examData),
        EXAM_ERROR
    );
};

// Update exam
export const updateExam = (examId, examData) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        UPDATE_EXAM,
        () => api.put(`/exams/${examId}`, examData),
        EXAM_ERROR
    );
};

// Delete exam
export const deleteExam = (examId) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        DELETE_EXAM,
        () => api.delete(`/exams/${examId}`),
        EXAM_ERROR
    );
};

// Toggle exam status
export const toggleExamStatus = (examId) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        TOGGLE_EXAM_STATUS,
        () => api.post(`/exams/${examId}/toggle`, {}),
        EXAM_ERROR
    );
};

// Set current exam
export const setCurrentExam = (exam) => (dispatch) => {
    dispatch({
        type: SET_CURRENT_EXAM,
        payload: exam
    });
};

// Clear exam errors
export const clearExamErrors = () => (dispatch) => {
    dispatch({ type: CLEAR_EXAM_ERRORS });
}; 