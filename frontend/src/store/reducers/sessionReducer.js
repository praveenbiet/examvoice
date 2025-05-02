import {
    START_SESSION,
    SUBMIT_ANSWER,
    GET_SESSION_RESULTS,
    EXTEND_SESSION_TIME,
    UPDATE_TIME_REMAINING,
    SESSION_ERROR,
    CLEAR_SESSION_ERRORS,
    SET_CURRENT_SESSION
} from '../types';

const initialState = {
    currentSession: null,
    timeRemaining: null,
    responses: [],
    loading: false,
    error: null
};

export default (state = initialState, action) => {
    switch (action.type) {
        case START_SESSION:
            return {
                ...state,
                currentSession: action.payload,
                loading: false
            };
        case SUBMIT_ANSWER:
            return {
                ...state,
                responses: [...state.responses, action.payload],
                loading: false
            };
        case GET_SESSION_RESULTS:
            return {
                ...state,
                currentSession: action.payload.session,
                responses: action.payload.responses,
                loading: false
            };
        case EXTEND_SESSION_TIME:
            return {
                ...state,
                currentSession: {
                    ...state.currentSession,
                    extended_minutes: action.payload
                },
                loading: false
            };
        case UPDATE_TIME_REMAINING:
            return {
                ...state,
                timeRemaining: action.payload
            };
        case SET_CURRENT_SESSION:
            return {
                ...state,
                currentSession: action.payload
            };
        case SESSION_ERROR:
            return {
                ...state,
                error: action.payload,
                loading: false
            };
        case CLEAR_SESSION_ERRORS:
            return {
                ...state,
                error: null
            };
        default:
            return state;
    }
}; 