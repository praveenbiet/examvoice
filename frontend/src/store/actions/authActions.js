import api, { createAuthenticatedCall, createAuthenticatedCallWithToken } from '../../utils/api';
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
    const token = getState().auth.token;
    if (!token) return;

    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        USER_LOADED,
        () => api.get('/auth/profile'),
        AUTH_ERROR
    );
};

// Register User
export const register = (userData) => async (dispatch) => {
    return createAuthenticatedCall(
        dispatch,
        REGISTER_SUCCESS,
        () => api.post('/auth/register', userData),
        REGISTER_FAIL
    ).then(() => dispatch(loadUser()));
};

// Login User
export const login = (userData) => async (dispatch) => {
    return createAuthenticatedCall(
        dispatch,
        LOGIN_SUCCESS,
        () => api.post('/auth/login', userData),
        LOGIN_FAIL
    ).then(() => dispatch(loadUser()));
};

// Logout User
export const logout = () => (dispatch) => {
    dispatch({ type: LOGOUT });
};

// Update Profile
export const updateProfile = (profileData) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        USER_LOADED,
        () => api.put('/auth/profile', profileData),
        AUTH_ERROR
    );
};

// Change Password
export const changePassword = (passwordData) => async (dispatch, getState) => {
    return createAuthenticatedCallWithToken(
        dispatch,
        getState,
        USER_LOADED,
        () => api.put('/auth/password', passwordData),
        AUTH_ERROR
    ).then(() => dispatch(loadUser()));
};

// Clear Errors
export const clearErrors = () => (dispatch) => {
    dispatch({ type: CLEAR_ERRORS });
}; 