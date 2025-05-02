import axios from 'axios';
import {
    REGISTER_SUCCESS,
    REGISTER_FAIL,
    LOGIN_SUCCESS,
    LOGIN_FAIL,
    LOGOUT,
    USER_LOADED,
    AUTH_ERROR,
    CLEAR_ERRORS
} from '../types';

// Load User
export const loadUser = () => async (dispatch, getState) => {
    try {
        const token = getState().auth.token;
        if (!token) return;

        const config = {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        };

        const res = await axios.get('/api/profile', config);
        dispatch({
            type: USER_LOADED,
            payload: res.data
        });
    } catch (err) {
        dispatch({
            type: AUTH_ERROR,
            payload: err.response?.data?.message || 'Error loading user'
        });
    }
};

// Register User
export const register = (userData) => async (dispatch) => {
    try {
        const res = await axios.post('/api/register', userData);
        dispatch({
            type: REGISTER_SUCCESS,
            payload: res.data
        });
        dispatch(loadUser());
    } catch (err) {
        dispatch({
            type: REGISTER_FAIL,
            payload: err.response?.data?.message || 'Registration failed'
        });
    }
};

// Login User
export const login = (userData) => async (dispatch) => {
    try {
        const res = await axios.post('/api/login', userData);
        dispatch({
            type: LOGIN_SUCCESS,
            payload: res.data
        });
        dispatch(loadUser());
    } catch (err) {
        dispatch({
            type: LOGIN_FAIL,
            payload: err.response?.data?.message || 'Login failed'
        });
    }
};

// Logout User
export const logout = () => (dispatch) => {
    dispatch({ type: LOGOUT });
};

// Clear Errors
export const clearErrors = () => (dispatch) => {
    dispatch({ type: CLEAR_ERRORS });
}; 