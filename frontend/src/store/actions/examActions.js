import axios from 'axios';
import {
    GET_EXAMS,
    GET_EXAM,
    GET_SCHEDULED_EXAMS,
    CREATE_EXAM,
    UPDATE_EXAM,
    DELETE_EXAM,
    TOGGLE_EXAM_STATUS,
    SET_CURRENT_EXAM,
    EXAM_ERROR,
    CLEAR_EXAM_ERRORS
} from '../types';

// Get all exams
export const getExams = () => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.get('/api/exams', config);
        dispatch({
            type: GET_EXAMS,
            payload: res.data.exams
        });
    } catch (err) {
        dispatch({
            type: EXAM_ERROR,
            payload: err.response?.data?.message || 'Error fetching exams'
        });
    }
};

// Get single exam
export const getExam = (examId) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.get(`/api/exams/${examId}`, config);
        dispatch({
            type: GET_EXAM,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: EXAM_ERROR,
            payload: err.response?.data?.message || 'Error fetching exam'
        });
    }
};

// Get scheduled exams
export const getScheduledExams = () => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.get('/api/exams/scheduled', config);
        dispatch({
            type: GET_SCHEDULED_EXAMS,
            payload: res.data.scheduled_exams
        });
    } catch (err) {
        dispatch({
            type: EXAM_ERROR,
            payload: err.response?.data?.message || 'Error fetching scheduled exams'
        });
    }
};

// Create exam
export const createExam = (examData) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.post('/api/exams', examData, config);
        dispatch({
            type: CREATE_EXAM,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: EXAM_ERROR,
            payload: err.response?.data?.message || 'Error creating exam'
        });
    }
};

// Toggle exam status
export const toggleExamStatus = (examId) => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.post(`/api/exams/${examId}/toggle`, {}, config);
        dispatch({
            type: TOGGLE_EXAM_STATUS,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: EXAM_ERROR,
            payload: err.response?.data?.message || 'Error toggling exam status'
        });
    }
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