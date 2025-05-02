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

const initialState = {
    exams: [],
    currentExam: null,
    scheduledExams: [],
    loading: false,
    error: null
};

export default (state = initialState, action) => {
    switch (action.type) {
        case GET_EXAMS:
            return {
                ...state,
                exams: action.payload,
                loading: false
            };
        case GET_EXAM:
            return {
                ...state,
                currentExam: action.payload,
                loading: false
            };
        case GET_SCHEDULED_EXAMS:
            return {
                ...state,
                scheduledExams: action.payload,
                loading: false
            };
        case CREATE_EXAM:
            return {
                ...state,
                exams: [...state.exams, action.payload],
                loading: false
            };
        case UPDATE_EXAM:
            return {
                ...state,
                exams: state.exams.map(exam =>
                    exam.id === action.payload.id ? action.payload : exam
                ),
                loading: false
            };
        case DELETE_EXAM:
            return {
                ...state,
                exams: state.exams.filter(exam => exam.id !== action.payload),
                loading: false
            };
        case TOGGLE_EXAM_STATUS:
            return {
                ...state,
                exams: state.exams.map(exam =>
                    exam.id === action.payload.id ? action.payload : exam
                ),
                loading: false
            };
        case SET_CURRENT_EXAM:
            return {
                ...state,
                currentExam: action.payload
            };
        case EXAM_ERROR:
            return {
                ...state,
                error: action.payload,
                loading: false
            };
        case CLEAR_EXAM_ERRORS:
            return {
                ...state,
                error: null
            };
        default:
            return state;
    }
}; 