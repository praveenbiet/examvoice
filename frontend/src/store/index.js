import { createStore, combineReducers, applyMiddleware } from 'redux';
import thunk from 'redux-thunk';
import { composeWithDevTools } from 'redux-devtools-extension';
import authReducer from './reducers/authReducer';
import examReducer from './reducers/examReducer';
import sessionReducer from './reducers/sessionReducer';

const rootReducer = combineReducers({
    auth: authReducer,
    exam: examReducer,
    session: sessionReducer
});

const initialState = {
    auth: {
        user: null,
        token: localStorage.getItem('token'),
        isAuthenticated: !!localStorage.getItem('token'),
        loading: false,
        error: null
    },
    exam: {
        exams: [],
        currentExam: null,
        scheduledExams: [],
        loading: false,
        error: null
    },
    session: {
        currentSession: null,
        timeRemaining: null,
        responses: [],
        loading: false,
        error: null
    }
};

const middleware = [thunk];

const store = createStore(
    rootReducer,
    initialState,
    composeWithDevTools(applyMiddleware(...middleware))
);

export default store; 