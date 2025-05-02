from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from models import SpeechRecognition, TextToSpeech, AnswerEvaluator, VoiceRecognition, User, Exam, Question, ExamSession, ExamResponse, VoiceProfile, ExamProgress
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import io
import speech_recognition as sr
from gtts import gTTS
import openai
import json
import jwt
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from logging.handlers import RotatingFileHandler
import traceback
from TTS.api import TTS
import librosa
import sounddevice as sd
import numpy as np
import noisereduce as nr
from pydub import AudioSegment
import matplotlib.pyplot as plt
import seaborn as sns
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
logger.addHandler(handler)

app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exam.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# Initialize ML models
speech_recognition = SpeechRecognition()
text_to_speech = TextToSpeech()
answer_evaluator = AnswerEvaluator()
voice_recognition = VoiceRecognition()

# Store active sessions
active_sessions = {}

# Ensure audio_responses directory exists
os.makedirs('audio_responses', exist_ok=True)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Custom error classes
class ValidationError(Exception):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}

class AuthenticationError(Exception):
    pass

class ResourceNotFoundError(Exception):
    pass

class RateLimitError(Exception):
    pass

# JWT Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            token = token.split(' ')[1]  # Remove 'Bearer ' prefix
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(data['user_id'])
            if not current_user:
                return jsonify({'message': 'User not found'}), 401
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.String(500), nullable=False)
    correct_answer = db.Column(db.String(1000), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    voice_instruction = db.Column(db.String(500), nullable=True)

class ExamResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.String(100), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    candidate_answer = db.Column(db.String(1000), nullable=False)
    similarity_score = db.Column(db.Float, nullable=False)
    audio_path = db.Column(db.String(500), nullable=True)
    feedback_audio_path = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ExamSession:
    def __init__(self, candidate_id, voice_profile_path):
        self.candidate_id = candidate_id
        self.current_question_id = None
        self.voice_profile_path = voice_profile_path
        self.is_completed = False
        self.last_activity = datetime.now()

# Initialize TTS model for voice cloning
tts = TTS(model_name="tts_models/multilingual/multi-dataset/your_tts", progress_bar=False)

# Initialize voice quality check components
recognizer = sr.Recognizer()

def validate_voice_sample(audio_path):
    """Validate voice sample quality and characteristics"""
    try:
        # Load audio file
        audio, sr = librosa.load(audio_path, sr=16000)
        
        # Check duration
        duration = librosa.get_duration(y=audio, sr=sr)
        if duration < 5:
            raise ValidationError("Voice sample too short. Please provide at least 5 seconds of speech.")
        if duration > 60:
            raise ValidationError("Voice sample too long. Please provide no more than 60 seconds of speech.")
        
        # Check audio quality
        rms = librosa.feature.rms(y=audio)[0]
        if np.mean(rms) < 0.01:
            raise ValidationError("Audio too quiet. Please speak louder.")
        
        # Check for background noise
        noise_reduced = nr.reduce_noise(y=audio, sr=sr)
        noise_level = np.mean(np.abs(audio - noise_reduced))
        if noise_level > 0.1:
            raise ValidationError("Too much background noise. Please record in a quiet environment.")
        
        # Check for speech content
        with sr.AudioFile(audio_path) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data)
                if len(text.split()) < 10:
                    raise ValidationError("Not enough speech content. Please speak more words.")
            except sr.UnknownValueError:
                raise ValidationError("Could not detect speech. Please ensure you are speaking clearly.")
        
        return {
            'duration': duration,
            'noise_level': noise_level,
            'rms_level': np.mean(rms),
            'is_valid': True
        }
    except Exception as e:
        raise ValidationError(f"Voice sample validation failed: {str(e)}")

def process_voice_sample(audio_path):
    """Process and enhance voice sample"""
    try:
        # Load audio
        audio, sr = librosa.load(audio_path, sr=16000)
        
        # Remove background noise
        audio_clean = nr.reduce_noise(y=audio, sr=sr)
        
        # Normalize volume
        audio_norm = librosa.util.normalize(audio_clean)
        
        # Save processed audio
        processed_path = audio_path.replace('.wav', '_processed.wav')
        librosa.output.write_wav(processed_path, audio_norm, sr)
        
        return processed_path
    except Exception as e:
        raise ValidationError(f"Voice sample processing failed: {str(e)}")

@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/start_exam', methods=['POST'])
def start_exam():
    try:
        data = request.json
        candidate_id = data.get('candidateId')
        exam_id = data.get('examId')
        
        # Load exam questions
        with open('exam_questions.json', 'r') as f:
            exam_data = json.load(f)
            questions = exam_data.get('questions', [])
        
        # Initialize exam session
        exam_session = {
            'candidate_id': candidate_id,
            'exam_id': exam_id,
            'current_question_index': 0,
            'start_time': datetime.now().isoformat(),
            'responses': []
        }
        
        # Save exam session
        with open(f'exam_sessions/{candidate_id}_{exam_id}.json', 'w') as f:
            json.dump(exam_session, f)
        
        return jsonify({
            'success': True,
            'message': 'Exam started successfully',
            'question': questions[0]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/record_response', methods=['POST'])
def record_response():
    try:
        audio_file = request.files['audio']
        candidate_id = request.form.get('candidateId')
        exam_id = request.form.get('examId')
        
        # Save the audio file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        audio_filename = f'audio_responses/{candidate_id}_{exam_id}_{timestamp}.wav'
        audio_file.save(audio_filename)
        
        # Load exam session
        session_file = f'exam_sessions/{candidate_id}_{exam_id}.json'
        with open(session_file, 'r') as f:
            exam_session = json.load(f)
        
        # Update session with audio file path
        exam_session['responses'].append({
            'question_index': exam_session['current_question_index'],
            'audio_file': audio_filename,
            'timestamp': datetime.now().isoformat()
        })
        
        # Save updated session
        with open(session_file, 'w') as f:
            json.dump(exam_session, f)
        
        return jsonify({'success': True, 'message': 'Response recorded successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/get_response_audio/<candidate_id>/<exam_id>/<question_index>', methods=['GET'])
def get_response_audio(candidate_id, exam_id, question_index):
    try:
        # Load exam session
        session_file = f'exam_sessions/{candidate_id}_{exam_id}.json'
        with open(session_file, 'r') as f:
            exam_session = json.load(f)
        
        # Find the response for the requested question
        response = next((r for r in exam_session['responses'] 
                        if r['question_index'] == int(question_index)), None)
        
        if response and os.path.exists(response['audio_file']):
            return send_file(response['audio_file'], mimetype='audio/wav')
        else:
            return jsonify({'success': False, 'error': 'Audio file not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/verify_identity', methods=['POST'])
def verify_identity():
    try:
        candidate_id = request.form.get('candidate_id')
        voice_sample = request.files.get('voice_sample')
        
        if not candidate_id or not voice_sample:
            return jsonify({'error': 'Missing required data'}), 400
        
        # Save temporary voice sample
        temp_path = f"temp/{candidate_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        os.makedirs('temp', exist_ok=True)
        voice_sample.save(temp_path)
        
        # Verify speaker
        is_verified = voice_recognition.verify_speaker(temp_path, candidate_id)
        
        # Clean up temporary file
        os.remove(temp_path)
        
        if not is_verified:
            return jsonify({'error': 'Voice verification failed'}), 401
        
        # Get exam session
        session = active_sessions.get(candidate_id)
        if not session:
            return jsonify({'error': 'No active exam session found'}), 404
        
        # Update last activity
        session.last_activity = datetime.now()
        
        return jsonify({
            'status': 'success',
            'message': 'Identity verified',
            'current_question_id': session.current_question_id,
            'is_completed': session.is_completed
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_question', methods=['GET'])
def get_question():
    try:
        candidate_id = request.args.get('candidate_id')
        if not candidate_id:
            return jsonify({'error': 'Candidate ID required'}), 400
        
        # Get exam session
        session = active_sessions.get(candidate_id)
        if not session:
            return jsonify({'error': 'No active exam session found'}), 404
        
        # Get current or next question
        if session.current_question_id:
            question = Question.query.get(session.current_question_id)
        else:
            question = Question.query.first()
            session.current_question_id = question.id
        
        return jsonify({
            'question_id': question.id,
            'question_text': question.question_text,
            'voice_instruction': question.voice_instruction
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process_answer', methods=['POST'])
def process_answer():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        question_id = request.form.get('question_id')
        candidate_id = request.form.get('candidate_id')
        
        if not audio_file or not question_id or not candidate_id:
            return jsonify({'error': 'Missing required data'}), 400

        # Save audio file
        audio_path = f"uploads/{candidate_id}_{question_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        os.makedirs('uploads', exist_ok=True)
        audio_file.save(audio_path)
        
        # Convert speech to text
        candidate_answer = speech_recognition.transcribe(audio_path)
        
        # Get correct answer
        question = Question.query.get(question_id)
        
        # Evaluate answer
        similarity_score = answer_evaluator.evaluate_similarity(
            candidate_answer, 
            question.correct_answer
        )
        
        # Generate feedback audio
        feedback_text = f"Your answer was {similarity_score*100:.2f}% similar to the correct answer."
        feedback_audio_path = text_to_speech.synthesize(feedback_text)
        
        # Update exam session
        session = active_sessions.get(candidate_id)
        if session:
            # Get next question
            next_question = Question.query.filter(Question.id > question_id).first()
            if next_question:
                session.current_question_id = next_question.id
            else:
                session.is_completed = True
            session.last_activity = datetime.now()
        
        return jsonify({
            'status': 'success',
            'similarity_score': similarity_score,
            'feedback_audio_path': feedback_audio_path,
            'transcribed_text': candidate_answer,
            'is_completed': session.is_completed if session else False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_audio/<int:result_id>', methods=['GET'])
def get_audio(result_id):
    result = ExamResult.query.get_or_404(result_id)
    audio_type = request.args.get('type', 'answer')  # 'answer' or 'feedback'
    
    if audio_type == 'answer':
        audio_path = result.audio_path
    else:
        audio_path = result.feedback_audio_path
    
    if not audio_path or not os.path.exists(audio_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    return send_file(
        audio_path,
        mimetype='audio/wav',
        as_attachment=True,
        download_name=f'{audio_type}_{result_id}.wav'
    )

# User Registration
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if not data or not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Username already exists'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'Email already exists'}), 400
    
    hashed_password = generate_password_hash(data['password'])
    new_user = User(
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password,
        role=data.get('role', 'candidate')
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'User created successfully'}), 201

# User Login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    token = jwt.encode(
        {'user_id': user.id, 'exp': datetime.utcnow() + timedelta(days=1)},
        app.config['SECRET_KEY']
    )
    
    return jsonify({
        'token': token,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        }
    })

# Get User Profile
@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'role': current_user.role,
        'created_at': current_user.created_at.isoformat(),
        'last_login': current_user.last_login.isoformat() if current_user.last_login else None
    })

# Update User Profile
@app.route('/api/profile', methods=['PUT'])
@token_required
def update_profile(current_user):
    data = request.json
    if not data:
        return jsonify({'message': 'No data provided'}), 400
    
    if 'email' in data and data['email'] != current_user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'message': 'Email already exists'}), 400
        current_user.email = data['email']
    
    if 'password' in data:
        current_user.password_hash = generate_password_hash(data['password'])
    
    db.session.commit()
    return jsonify({'message': 'Profile updated successfully'})

# Create Voice Profile
@app.route('/api/voice-profile', methods=['POST'])
@token_required
def create_voice_profile(current_user):
    if 'voice_sample' not in request.files:
        return jsonify({'message': 'No voice sample provided'}), 400
    
    voice_sample = request.files['voice_sample']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'voice_profiles/{current_user.id}_{timestamp}.wav'
    
    os.makedirs('voice_profiles', exist_ok=True)
    voice_sample.save(filename)
    
    voice_profile = VoiceProfile(
        user_id=current_user.id,
        voice_sample_path=filename
    )
    
    db.session.add(voice_profile)
    db.session.commit()
    
    return jsonify({'message': 'Voice profile created successfully'}), 201

# Create Exam
@app.route('/api/exams', methods=['POST'])
@token_required
def create_exam(current_user):
    if current_user.role not in ['admin', 'examiner']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    data = request.json
    if not data or not data.get('title') or not data.get('questions'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    try:
        exam = Exam(
            title=data['title'],
            description=data.get('description', ''),
            creator_id=current_user.id,
            duration_minutes=data.get('duration_minutes', 60),
            passing_score=data.get('passing_score', 70.0)
        )
        db.session.add(exam)
        db.session.flush()  # Get exam.id without committing
        
        # Add questions
        for i, q in enumerate(data['questions']):
            question = Question(
                exam_id=exam.id,
                question_text=q['text'],
                correct_answer=q['correct_answer'],
                max_score=q.get('max_score', 10.0),
                order=i
            )
            db.session.add(question)
        
        db.session.commit()
        return jsonify({'message': 'Exam created successfully', 'exam_id': exam.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

# Get Exam Details
@app.route('/api/exams/<int:exam_id>', methods=['GET'])
@token_required
def get_exam(current_user, exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if current_user.role == 'candidate' and not exam.is_active:
        return jsonify({'message': 'Exam is not active'}), 403
    
    questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.order).all()
    return jsonify({
        'exam': {
            'id': exam.id,
            'title': exam.title,
            'description': exam.description,
            'duration_minutes': exam.duration_minutes,
            'passing_score': exam.passing_score,
            'is_active': exam.is_active
        },
        'questions': [{
            'id': q.id,
            'text': q.question_text,
            'max_score': q.max_score,
            'order': q.order
        } for q in questions]
    })

# Start Exam Session
@app.route('/api/exams/<int:exam_id>/start', methods=['POST'])
@token_required
def start_exam_session(current_user, exam_id):
    if current_user.role != 'candidate':
        return jsonify({'message': 'Only candidates can start exams'}), 403
    
    exam = Exam.query.get_or_404(exam_id)
    if not exam.is_active:
        return jsonify({'message': 'Exam is not active'}), 403
    
    # Check if user already has an active session
    active_session = ExamSession.query.filter_by(
        exam_id=exam_id,
        candidate_id=current_user.id,
        status='in_progress'
    ).first()
    
    if active_session:
        return jsonify({'message': 'You already have an active session', 'session_id': active_session.id})
    
    # Create new session
    session = ExamSession(
        exam_id=exam_id,
        candidate_id=current_user.id
    )
    db.session.add(session)
    db.session.commit()
    
    return jsonify({
        'message': 'Exam session started',
        'session_id': session.id,
        'start_time': session.start_time.isoformat()
    })

# Submit Answer
@app.route('/api/sessions/<int:session_id>/answers', methods=['POST'])
@token_required
def submit_answer(current_user, session_id):
    session = ExamSession.query.get_or_404(session_id)
    if session.candidate_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403
    
    if session.status != 'in_progress':
        return jsonify({'message': 'Session is not active'}), 400
    
    if 'audio' not in request.files:
        return jsonify({'message': 'No audio file provided'}), 400
    
    audio_file = request.files['audio']
    question_id = request.form.get('question_id')
    if not question_id:
        return jsonify({'message': 'Question ID is required'}), 400
    
    try:
        # Save audio file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        audio_filename = f'audio_responses/{session_id}_{question_id}_{timestamp}.wav'
        audio_file.save(audio_filename)
        
        # Transcribe audio
        transcribed_text = speech_recognition.transcribe(audio_filename)
        
        # Get question and evaluate answer
        question = Question.query.get_or_404(question_id)
        similarity_score = answer_evaluator.evaluate_similarity(
            transcribed_text,
            question.correct_answer
        )
        
        # Calculate score
        score = similarity_score * question.max_score
        
        # Create response
        response = ExamResponse(
            session_id=session_id,
            question_id=question_id,
            audio_path=audio_filename,
            transcribed_text=transcribed_text,
            score=score
        )
        db.session.add(response)
        
        # Update session score
        session.total_score = sum(r.score for r in session.responses)
        
        # Check if exam is complete
        total_questions = Question.query.filter_by(exam_id=session.exam_id).count()
        if len(session.responses) + 1 >= total_questions:
            session.status = 'completed'
            session.end_time = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': 'Answer submitted successfully',
            'score': score,
            'transcribed_text': transcribed_text
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

# Get Session Results
@app.route('/api/sessions/<int:session_id>/results', methods=['GET'])
@token_required
def get_session_results(current_user, session_id):
    session = ExamSession.query.get_or_404(session_id)
    if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    responses = ExamResponse.query.filter_by(session_id=session_id).all()
    exam = Exam.query.get(session.exam_id)
    
    return jsonify({
        'session': {
            'id': session.id,
            'start_time': session.start_time.isoformat(),
            'end_time': session.end_time.isoformat() if session.end_time else None,
            'status': session.status,
            'total_score': session.total_score,
            'passing_score': exam.passing_score,
            'passed': session.total_score >= exam.passing_score if session.status == 'completed' else None
        },
        'responses': [{
            'question_id': r.question_id,
            'score': r.score,
            'transcribed_text': r.transcribed_text,
            'feedback': r.feedback
        } for r in responses]
    })

# List Exams
@app.route('/api/exams', methods=['GET'])
@token_required
def list_exams(current_user):
    if current_user.role in ['admin', 'examiner']:
        exams = Exam.query.order_by(Exam.created_at.desc()).all()
    else:
        exams = Exam.query.filter_by(is_active=True).order_by(Exam.created_at.desc()).all()
    
    return jsonify({
        'exams': [{
            'id': exam.id,
            'title': exam.title,
            'description': exam.description,
            'duration_minutes': exam.duration_minutes,
            'passing_score': exam.passing_score,
            'is_active': exam.is_active,
            'created_at': exam.created_at.isoformat(),
            'question_count': len(exam.questions)
        } for exam in exams]
    })

# Toggle Exam Status
@app.route('/api/exams/<int:exam_id>/toggle', methods=['POST'])
@token_required
def toggle_exam_status(current_user, exam_id):
    if current_user.role not in ['admin', 'examiner']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    exam = Exam.query.get_or_404(exam_id)
    if exam.creator_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'You can only toggle your own exams'}), 403
    
    exam.is_active = not exam.is_active
    db.session.commit()
    
    return jsonify({
        'message': f'Exam {"activated" if exam.is_active else "deactivated"} successfully',
        'is_active': exam.is_active
    })

# Get Candidate Progress
@app.route('/api/candidates/<int:candidate_id>/progress', methods=['GET'])
@token_required
def get_candidate_progress(current_user, candidate_id):
    if current_user.role not in ['admin', 'examiner'] and current_user.id != candidate_id:
        return jsonify({'message': 'Unauthorized'}), 403
    
    sessions = ExamSession.query.filter_by(candidate_id=candidate_id).all()
    progress = []
    
    for session in sessions:
        exam = Exam.query.get(session.exam_id)
        total_questions = len(exam.questions)
        completed_questions = len(session.responses)
        
        progress.append({
            'exam_id': exam.id,
            'exam_title': exam.title,
            'session_id': session.id,
            'status': session.status,
            'progress': f"{completed_questions}/{total_questions}",
            'percentage': (completed_questions / total_questions) * 100 if total_questions > 0 else 0,
            'total_score': session.total_score,
            'passing_score': exam.passing_score,
            'start_time': session.start_time.isoformat(),
            'end_time': session.end_time.isoformat() if session.end_time else None
        })
    
    return jsonify({'progress': progress})

# Get Exam Statistics
@app.route('/api/exams/<int:exam_id>/statistics', methods=['GET'])
@token_required
def get_exam_statistics(current_user, exam_id):
    if current_user.role not in ['admin', 'examiner']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    exam = Exam.query.get_or_404(exam_id)
    sessions = ExamSession.query.filter_by(exam_id=exam_id).all()
    
    if not sessions:
        return jsonify({'message': 'No sessions found for this exam'}), 404
    
    # Calculate statistics
    total_candidates = len(sessions)
    completed_sessions = sum(1 for s in sessions if s.status == 'completed')
    passed_sessions = sum(1 for s in sessions if s.status == 'completed' and s.total_score >= exam.passing_score)
    
    # Calculate average scores
    completed_scores = [s.total_score for s in sessions if s.status == 'completed']
    average_score = sum(completed_scores) / len(completed_scores) if completed_scores else 0
    
    # Get question-wise statistics
    question_stats = []
    for question in exam.questions:
        responses = ExamResponse.query.filter_by(question_id=question.id).all()
        if responses:
            avg_score = sum(r.score for r in responses) / len(responses)
            question_stats.append({
                'question_id': question.id,
                'average_score': avg_score,
                'max_score': question.max_score,
                'response_count': len(responses)
            })
    
    return jsonify({
        'exam_id': exam.id,
        'title': exam.title,
        'statistics': {
            'total_candidates': total_candidates,
            'completed_sessions': completed_sessions,
            'passed_sessions': passed_sessions,
            'pass_rate': (passed_sessions / completed_sessions * 100) if completed_sessions > 0 else 0,
            'average_score': average_score,
            'question_statistics': question_stats
        }
    })

# Get Active Session
@app.route('/api/candidates/<int:candidate_id>/active-session', methods=['GET'])
@token_required
def get_active_session(current_user, candidate_id):
    if current_user.role not in ['admin', 'examiner'] and current_user.id != candidate_id:
        return jsonify({'message': 'Unauthorized'}), 403
    
    active_session = ExamSession.query.filter_by(
        candidate_id=candidate_id,
        status='in_progress'
    ).first()
    
    if not active_session:
        return jsonify({'message': 'No active session found'}), 404
    
    exam = Exam.query.get(active_session.exam_id)
    current_question = None
    
    # Find the next unanswered question
    answered_question_ids = [r.question_id for r in active_session.responses]
    next_question = Question.query.filter(
        Question.exam_id == exam.id,
        Question.id.notin_(answered_question_ids)
    ).order_by(Question.order).first()
    
    if next_question:
        current_question = {
            'id': next_question.id,
            'text': next_question.question_text,
            'order': next_question.order
        }
    
    return jsonify({
        'session_id': active_session.id,
        'exam_id': exam.id,
        'exam_title': exam.title,
        'start_time': active_session.start_time.isoformat(),
        'time_elapsed': (datetime.utcnow() - active_session.start_time).total_seconds() / 60,
        'time_remaining': exam.duration_minutes - (datetime.utcnow() - active_session.start_time).total_seconds() / 60,
        'current_question': current_question,
        'answered_questions': len(answered_question_ids),
        'total_questions': len(exam.questions)
    })

# Schedule Exam
@app.route('/api/exams/<int:exam_id>/schedule', methods=['POST'])
@token_required
def schedule_exam(current_user, exam_id):
    if current_user.role not in ['admin', 'examiner']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    data = request.json
    if not data or not data.get('start_time') or not data.get('end_time'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    try:
        start_time = datetime.fromisoformat(data['start_time'])
        end_time = datetime.fromisoformat(data['end_time'])
        
        if start_time >= end_time:
            return jsonify({'message': 'End time must be after start time'}), 400
        
        exam = Exam.query.get_or_404(exam_id)
        exam.scheduled_start = start_time
        exam.scheduled_end = end_time
        exam.is_scheduled = True
        
        db.session.commit()
        return jsonify({
            'message': 'Exam scheduled successfully',
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat()
        })
    except ValueError:
        return jsonify({'message': 'Invalid date format'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

# Get Scheduled Exams
@app.route('/api/exams/scheduled', methods=['GET'])
@token_required
def get_scheduled_exams(current_user):
    now = datetime.utcnow()
    
    if current_user.role in ['admin', 'examiner']:
        scheduled_exams = Exam.query.filter(
            Exam.is_scheduled == True,
            Exam.scheduled_end > now
        ).order_by(Exam.scheduled_start).all()
    else:
        scheduled_exams = Exam.query.filter(
            Exam.is_scheduled == True,
            Exam.scheduled_end > now,
            Exam.is_active == True
        ).order_by(Exam.scheduled_start).all()
    
    return jsonify({
        'scheduled_exams': [{
            'id': exam.id,
            'title': exam.title,
            'start_time': exam.scheduled_start.isoformat(),
            'end_time': exam.scheduled_end.isoformat(),
            'duration_minutes': exam.duration_minutes,
            'time_until_start': (exam.scheduled_start - now).total_seconds() / 60 if exam.scheduled_start > now else 0,
            'status': 'upcoming' if exam.scheduled_start > now else 'in_progress' if now < exam.scheduled_end else 'completed'
        } for exam in scheduled_exams]
    })

# Extend Exam Time
@app.route('/api/sessions/<int:session_id>/extend', methods=['POST'])
@token_required
def extend_exam_time(current_user, session_id):
    session = ExamSession.query.get_or_404(session_id)
    if current_user.role not in ['admin', 'examiner'] and session.candidate_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403
    
    data = request.json
    if not data or not data.get('additional_minutes'):
        return jsonify({'message': 'Missing required fields'}), 400
    
    additional_minutes = int(data['additional_minutes'])
    if additional_minutes <= 0:
        return jsonify({'message': 'Additional minutes must be positive'}), 400
    
    exam = Exam.query.get(session.exam_id)
    if not exam.is_scheduled:
        return jsonify({'message': 'Exam is not scheduled'}), 400
    
    # Check if extension is within exam's scheduled end time
    max_extension = (exam.scheduled_end - datetime.utcnow()).total_seconds() / 60
    if additional_minutes > max_extension:
        return jsonify({
            'message': f'Cannot extend beyond exam end time. Maximum extension: {max_extension:.0f} minutes'
        }), 400
    
    session.extended_minutes = (session.extended_minutes or 0) + additional_minutes
    db.session.commit()
    
    return jsonify({
        'message': f'Exam time extended by {additional_minutes} minutes',
        'total_extension': session.extended_minutes,
        'new_end_time': (datetime.utcnow() + timedelta(minutes=exam.duration_minutes + session.extended_minutes)).isoformat()
    })

# Get Time Remaining
@app.route('/api/sessions/<int:session_id>/time', methods=['GET'])
@token_required
def get_time_remaining(current_user, session_id):
    session = ExamSession.query.get(session_id)
    if not session:
        return jsonify({'message': 'Session not found'}), 404
    
    time_remaining = session.get_time_remaining()
    socketio.emit('time_update', {'session_id': session_id, 'time_remaining': time_remaining}, room=str(session_id))
    
    return jsonify({'time_remaining': time_remaining})

# Auto-submit Incomplete Sessions
def auto_submit_incomplete_sessions():
    with app.app_context():
        now = datetime.utcnow()
        incomplete_sessions = ExamSession.query.filter(
            ExamSession.status == 'in_progress',
            ExamSession.start_time < now - timedelta(minutes=1)  # Add buffer time
        ).all()
        
        for session in incomplete_sessions:
            exam = Exam.query.get(session.exam_id)
            total_allowed_time = exam.duration_minutes + (session.extended_minutes or 0)
            
            if (now - session.start_time).total_seconds() / 60 >= total_allowed_time:
                session.status = 'completed'
                session.end_time = now
                db.session.commit()

# Schedule auto-submit task
scheduler = BackgroundScheduler()
scheduler.add_job(auto_submit_incomplete_sessions, 'interval', minutes=1)
scheduler.start()

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('join_session')
def handle_join_session(data):
    session_id = data.get('session_id')
    if session_id:
        join_room(str(session_id))
        emit('session_joined', {'session_id': session_id}, room=str(session_id))

@socketio.on('leave_session')
def handle_leave_session(data):
    session_id = data.get('session_id')
    if session_id:
        leave_room(str(session_id))
        emit('session_left', {'session_id': session_id}, room=str(session_id))

@socketio.on('question_answered')
def handle_question_answered(data):
    session_id = data.get('session_id')
    question_id = data.get('question_id')
    if session_id and question_id:
        emit('answer_submitted', {
            'session_id': session_id,
            'question_id': question_id,
            'timestamp': datetime.utcnow().isoformat()
        }, room=str(session_id))

@socketio.on('session_status')
def handle_session_status(data):
    session_id = data.get('session_id')
    if session_id:
        session = ExamSession.query.get(session_id)
        if session:
            emit('status_update', {
                'session_id': session_id,
                'status': session.status,
                'progress': len(session.responses),
                'total_questions': len(session.exam.questions)
            }, room=str(session_id))

@socketio.on('exam_completed')
def handle_exam_completed(data):
    session_id = data.get('session_id')
    if session_id:
        session = ExamSession.query.get(session_id)
        if session:
            emit('results_ready', {
                'session_id': session_id,
                'score': session.total_score,
                'passing_score': session.exam.passing_score,
                'passed': session.total_score >= session.exam.passing_score
            }, room=str(session_id))

# Session state synchronization
@app.route('/api/sessions/<int:session_id>/sync', methods=['POST'])
@token_required
def sync_session_state(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            return jsonify({'message': 'Unauthorized'}), 403

        data = request.json
        if not data:
            return jsonify({'message': 'No data provided'}), 400

        # Update session state
        if 'status' in data:
            session.status = data['status']
        if 'current_question' in data:
            session.current_question_id = data['current_question']
        if 'time_remaining' in data:
            session.time_remaining = data['time_remaining']

        db.session.commit()

        # Broadcast state update
        socketio.emit('session_state_update', {
            'session_id': session_id,
            'status': session.status,
            'current_question': session.current_question_id,
            'time_remaining': session.time_remaining
        }, room=str(session_id))

        return jsonify({'message': 'Session state synchronized'})
    except Exception as e:
        return handle_db_error(e)

# Batch synchronization for multiple sessions
@app.route('/api/sessions/sync', methods=['POST'])
@token_required
def sync_multiple_sessions(current_user):
    try:
        data = request.json
        if not data or not isinstance(data, list):
            return jsonify({'message': 'Invalid data format'}), 400

        results = []
        for session_data in data:
            session_id = session_data.get('session_id')
            if not session_id:
                continue

            session = ExamSession.query.get(session_id)
            if not session:
                continue

            if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
                continue

            # Update session state
            if 'status' in session_data:
                session.status = session_data['status']
            if 'current_question' in session_data:
                session.current_question_id = session_data['current_question']
            if 'time_remaining' in session_data:
                session.time_remaining = session_data['time_remaining']

            results.append({
                'session_id': session_id,
                'status': session.status,
                'current_question': session.current_question_id,
                'time_remaining': session.time_remaining
            })

        db.session.commit()

        # Broadcast updates for each session
        for result in results:
            socketio.emit('session_state_update', result, room=str(result['session_id']))

        return jsonify({'message': 'Sessions synchronized', 'results': results})
    except Exception as e:
        return handle_db_error(e)

# Progress tracking endpoints
@app.route('/api/sessions/<int:session_id>/progress', methods=['GET'])
@token_required
def get_session_progress(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        # Update progress metrics
        session.update_progress()
        
        # Get detailed progress
        progress = ExamProgress.query.filter_by(session_id=session_id).all()
        
        return jsonify({
            'session_id': session_id,
            'total_questions': session.total_questions,
            'questions_answered': session.questions_answered,
            'questions_skipped': session.questions_skipped,
            'progress_percentage': session.progress_percentage,
            'average_time_per_question': session.average_time_per_question,
            'time_remaining': session.time_remaining,
            'difficulty_distribution': session.difficulty_distribution,
            'last_activity': session.last_activity.isoformat(),
            'detailed_progress': [{
                'question_id': p.question_id,
                'status': p.status,
                'time_spent': p.time_spent,
                'attempts': p.attempts,
                'confidence_score': p.confidence_score,
                'difficulty_rating': p.difficulty_rating
            } for p in progress]
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/sessions/<int:session_id>/progress/update', methods=['POST'])
@token_required
def update_question_progress(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id:
            raise AuthenticationError("Unauthorized")
        
        data = request.json
        if not data or 'question_id' not in data:
            raise ValidationError("Question ID is required")
        
        question_id = data['question_id']
        progress = ExamProgress.query.filter_by(
            session_id=session_id,
            question_id=question_id
        ).first()
        
        if not progress:
            progress = ExamProgress(
                session_id=session_id,
                question_id=question_id
            )
            db.session.add(progress)
        
        # Update progress
        if 'status' in data:
            progress.status = data['status']
        if 'difficulty_rating' in data:
            progress.difficulty_rating = data['difficulty_rating']
        if 'confidence_score' in data:
            progress.confidence_score = data['confidence_score']
        
        # Update time tracking
        if progress.status == 'completed':
            progress.end_time = datetime.utcnow()
            progress.time_spent = (progress.end_time - progress.start_time).total_seconds()
        
        progress.attempts += 1
        db.session.commit()
        
        # Update session and question metrics
        session.update_progress()
        progress.question.update_metrics()
        
        # Emit progress update
        socketio.emit('progress_update', {
            'session_id': session_id,
            'question_id': question_id,
            'status': progress.status,
            'progress_percentage': session.progress_percentage
        }, room=str(session_id))
        
        return jsonify({
            'message': 'Progress updated successfully',
            'progress': {
                'question_id': question_id,
                'status': progress.status,
                'time_spent': progress.time_spent,
                'attempts': progress.attempts
            }
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/sessions/<int:session_id>/progress/analytics', methods=['GET'])
@token_required
def get_progress_analytics(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        # Calculate analytics
        progress = ExamProgress.query.filter_by(session_id=session_id).all()
        
        # Time analytics
        time_spent = [p.time_spent for p in progress if p.time_spent]
        avg_time = sum(time_spent) / len(time_spent) if time_spent else 0
        
        # Difficulty analytics
        difficulties = [p.difficulty_rating for p in progress if p.difficulty_rating]
        difficulty_avg = sum(difficulties) / len(difficulties) if difficulties else 0
        
        # Confidence analytics
        confidences = [p.confidence_score for p in progress if p.confidence_score]
        confidence_avg = sum(confidences) / len(confidences) if confidences else 0
        
        # Performance metrics
        completed = len([p for p in progress if p.status == 'completed'])
        skipped = len([p for p in progress if p.status == 'skipped'])
        total = len(progress)
        
        return jsonify({
            'session_id': session_id,
            'time_analytics': {
                'average_time_per_question': avg_time,
                'total_time_spent': sum(time_spent),
                'time_distribution': {
                    '0-30s': len([t for t in time_spent if t <= 30]),
                    '30-60s': len([t for t in time_spent if 30 < t <= 60]),
                    '60-120s': len([t for t in time_spent if 60 < t <= 120]),
                    '120s+': len([t for t in time_spent if t > 120])
                }
            },
            'difficulty_analytics': {
                'average_difficulty': difficulty_avg,
                'distribution': session.difficulty_distribution
            },
            'confidence_analytics': {
                'average_confidence': confidence_avg,
                'distribution': {
                    'high': len([c for c in confidences if c >= 0.8]),
                    'medium': len([c for c in confidences if 0.5 <= c < 0.8]),
                    'low': len([c for c in confidences if c < 0.5])
                }
            },
            'performance_metrics': {
                'completed_questions': completed,
                'skipped_questions': skipped,
                'total_questions': total,
                'completion_rate': (completed / total * 100) if total > 0 else 0
            }
        })
    except Exception as e:
        return handle_generic_error(e)

# Progress visualization endpoints
@app.route('/api/sessions/<int:session_id>/progress/visualization/time', methods=['GET'])
@token_required
def get_time_visualization(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        progress = ExamProgress.query.filter_by(session_id=session_id).all()
        time_data = [p.time_spent for p in progress if p.time_spent]
        question_numbers = [i+1 for i, p in enumerate(progress) if p.time_spent]
        
        # Create time distribution plot
        plt.figure(figsize=(10, 6))
        sns.barplot(x=question_numbers, y=time_data)
        plt.title('Time Spent per Question')
        plt.xlabel('Question Number')
        plt.ylabel('Time (seconds)')
        plt.xticks(rotation=45)
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Convert to base64
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return jsonify({
            'image': image_base64,
            'data': {
                'question_numbers': question_numbers,
                'time_spent': time_data,
                'average_time': sum(time_data) / len(time_data) if time_data else 0
            }
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/sessions/<int:session_id>/progress/visualization/difficulty', methods=['GET'])
@token_required
def get_difficulty_visualization(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        progress = ExamProgress.query.filter_by(session_id=session_id).all()
        difficulties = [p.difficulty_rating for p in progress if p.difficulty_rating]
        question_numbers = [i+1 for i, p in enumerate(progress) if p.difficulty_rating]
        
        # Create difficulty distribution plot
        plt.figure(figsize=(10, 6))
        sns.barplot(x=question_numbers, y=difficulties)
        plt.title('Question Difficulty Ratings')
        plt.xlabel('Question Number')
        plt.ylabel('Difficulty (1-5)')
        plt.xticks(rotation=45)
        plt.ylim(1, 5)
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Convert to base64
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return jsonify({
            'image': image_base64,
            'data': {
                'question_numbers': question_numbers,
                'difficulties': difficulties,
                'average_difficulty': sum(difficulties) / len(difficulties) if difficulties else 0
            }
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/sessions/<int:session_id>/progress/visualization/confidence', methods=['GET'])
@token_required
def get_confidence_visualization(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        progress = ExamProgress.query.filter_by(session_id=session_id).all()
        confidences = [p.confidence_score for p in progress if p.confidence_score]
        question_numbers = [i+1 for i, p in enumerate(progress) if p.confidence_score]
        
        # Create confidence distribution plot
        plt.figure(figsize=(10, 6))
        sns.barplot(x=question_numbers, y=confidences)
        plt.title('Confidence Scores per Question')
        plt.xlabel('Question Number')
        plt.ylabel('Confidence Score (0-1)')
        plt.xticks(rotation=45)
        plt.ylim(0, 1)
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Convert to base64
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return jsonify({
            'image': image_base64,
            'data': {
                'question_numbers': question_numbers,
                'confidences': confidences,
                'average_confidence': sum(confidences) / len(confidences) if confidences else 0
            }
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/sessions/<int:session_id>/progress/visualization/completion', methods=['GET'])
@token_required
def get_completion_visualization(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        progress = ExamProgress.query.filter_by(session_id=session_id).all()
        completed = len([p for p in progress if p.status == 'completed'])
        skipped = len([p for p in progress if p.status == 'skipped'])
        pending = len([p for p in progress if p.status == 'pending'])
        
        # Create completion pie chart
        plt.figure(figsize=(8, 8))
        labels = ['Completed', 'Skipped', 'Pending']
        sizes = [completed, skipped, pending]
        colors = ['#2ecc71', '#e74c3c', '#f1c40f']
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        plt.title('Question Completion Status')
        plt.axis('equal')
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Convert to base64
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return jsonify({
            'image': image_base64,
            'data': {
                'completed': completed,
                'skipped': skipped,
                'pending': pending,
                'total': len(progress)
            }
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/sessions/<int:session_id>/progress/visualization/timeline', methods=['GET'])
@token_required
def get_timeline_visualization(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id and current_user.role not in ['admin', 'examiner']:
            raise AuthenticationError("Unauthorized")
        
        progress = ExamProgress.query.filter_by(session_id=session_id).order_by(ExamProgress.start_time).all()
        
        # Prepare timeline data
        timeline_data = []
        cumulative_time = 0
        for p in progress:
            if p.time_spent:
                cumulative_time += p.time_spent
                timeline_data.append({
                    'question_id': p.question_id,
                    'time_spent': p.time_spent,
                    'cumulative_time': cumulative_time,
                    'status': p.status,
                    'difficulty': p.difficulty_rating,
                    'confidence': p.confidence_score
                })
        
        # Create timeline plot
        plt.figure(figsize=(12, 6))
        x = [d['cumulative_time'] for d in timeline_data]
        y = [d['question_id'] for d in timeline_data]
        colors = ['#2ecc71' if d['status'] == 'completed' else '#e74c3c' if d['status'] == 'skipped' else '#f1c40f' for d in timeline_data]
        
        plt.scatter(x, y, c=colors, s=100)
        plt.plot(x, y, 'k--', alpha=0.3)
        plt.title('Exam Progress Timeline')
        plt.xlabel('Cumulative Time (seconds)')
        plt.ylabel('Question Number')
        
        # Save plot to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        # Convert to base64
        image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        return jsonify({
            'image': image_base64,
            'data': timeline_data
        })
    except Exception as e:
        return handle_generic_error(e)

# Error handlers
@app.errorhandler(ValidationError)
def handle_validation_error(error):
    logger.warning(f"Validation error: {str(error)}")
    return jsonify({
        'error': 'Validation Error',
        'message': str(error),
        'errors': error.errors
    }), 400

@app.errorhandler(AuthenticationError)
def handle_auth_error(error):
    logger.warning(f"Authentication error: {str(error)}")
    return jsonify({
        'error': 'Authentication Error',
        'message': str(error)
    }), 401

@app.errorhandler(ResourceNotFoundError)
def handle_not_found_error(error):
    logger.warning(f"Resource not found: {str(error)}")
    return jsonify({
        'error': 'Resource Not Found',
        'message': str(error)
    }), 404

@app.errorhandler(RateLimitError)
def handle_rate_limit_error(error):
    logger.warning(f"Rate limit exceeded: {str(error)}")
    return jsonify({
        'error': 'Rate Limit Exceeded',
        'message': str(error)
    }), 429

@app.errorhandler(Exception)
def handle_generic_error(error):
    logger.error(f"Unexpected error: {str(error)}\n{traceback.format_exc()}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred'
    }), 500

# WebSocket error handling
@socketio.on_error()
def handle_error(e):
    logger.error(f"WebSocket error: {str(e)}\n{traceback.format_exc()}")
    emit('error', {
        'error': 'WebSocket Error',
        'message': str(e)
    })

@socketio.on_error_default
def default_error_handler(e):
    logger.error(f"Default WebSocket error: {str(e)}\n{traceback.format_exc()}")
    emit('error', {
        'error': 'WebSocket Error',
        'message': str(e)
    })

# Database error handling
def handle_db_error(e):
    logger.error(f"Database error: {str(e)}\n{traceback.format_exc()}")
    db.session.rollback()
    return jsonify({
        'error': 'Database Error',
        'message': str(e)
    }), 500

# File upload error handling
def handle_file_upload_error(e):
    logger.error(f"File upload error: {str(e)}\n{traceback.format_exc()}")
    return jsonify({
        'error': 'File Upload Error',
        'message': str(e)
    }), 400

# Network error handling
def handle_network_error(e):
    logger.error(f"Network error: {str(e)}\n{traceback.format_exc()}")
    return jsonify({
        'error': 'Network Error',
        'message': str(e)
    }), 503

# Voice cloning endpoints
@app.route('/api/voice-clone/upload', methods=['POST'])
@token_required
def upload_voice_sample(current_user):
    try:
        if 'audio' not in request.files:
            raise ValidationError("No audio file provided")
        
        audio_file = request.files['audio']
        if not audio_file.filename.endswith(('.wav', '.mp3')):
            raise ValidationError("Invalid file format. Please upload WAV or MP3")
        
        # Create user's voice profile directory if it doesn't exist
        user_voice_dir = os.path.join('voice_profiles', str(current_user.id))
        os.makedirs(user_voice_dir, exist_ok=True)
        
        # Save the audio file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_path = os.path.join(user_voice_dir, f"sample_{timestamp}.wav")
        audio_file.save(audio_path)
        
        # Validate voice sample
        validation_result = validate_voice_sample(audio_path)
        
        # Process voice sample
        processed_path = process_voice_sample(audio_path)
        
        # Create voice profile
        voice_profile = VoiceProfile(
            user_id=current_user.id,
            audio_path=processed_path,
            created_at=datetime.utcnow(),
            sample_duration=validation_result['duration'],
            quality_score=validation_result['rms_level'] * (1 - validation_result['noise_level'])
        )
        db.session.add(voice_profile)
        db.session.commit()
        
        return jsonify({
            'message': 'Voice sample uploaded and validated successfully',
            'voice_profile_id': voice_profile.id,
            'validation': validation_result
        })
    except Exception as e:
        return handle_file_upload_error(e)

@app.route('/api/voice-clone/generate', methods=['POST'])
@token_required
def generate_cloned_voice(current_user):
    try:
        data = request.json
        if not data or 'text' not in data:
            raise ValidationError("Text is required")
        
        # Get user's voice profile
        voice_profile = VoiceProfile.query.filter_by(user_id=current_user.id).first()
        if not voice_profile:
            raise ResourceNotFoundError("No voice profile found. Please upload a voice sample first.")
        
        # Generate speech with cloned voice
        output_path = os.path.join('voice_profiles', str(current_user.id), f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
        tts.tts_to_file(
            text=data['text'],
            speaker_wav=voice_profile.audio_path,
            file_path=output_path
        )
        
        return send_file(output_path, mimetype='audio/wav')
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/voice-clone/status', methods=['GET'])
@token_required
def get_voice_clone_status(current_user):
    try:
        voice_profile = VoiceProfile.query.filter_by(user_id=current_user.id).first()
        if not voice_profile:
            return jsonify({'status': 'not_available'})
        
        return jsonify({
            'status': 'available',
            'created_at': voice_profile.created_at.isoformat(),
            'sample_duration': voice_profile.sample_duration if hasattr(voice_profile, 'sample_duration') else None
        })
    except Exception as e:
        return handle_generic_error(e)

@app.route('/api/voice-clone/quality', methods=['GET'])
@token_required
def get_voice_quality(current_user):
    try:
        voice_profile = VoiceProfile.query.filter_by(user_id=current_user.id).first()
        if not voice_profile:
            return jsonify({'status': 'not_available'})
        
        # Re-validate voice sample
        validation_result = validate_voice_sample(voice_profile.audio_path)
        
        return jsonify({
            'status': 'available',
            'quality_score': voice_profile.quality_score,
            'validation': validation_result,
            'recommendations': get_quality_recommendations(validation_result)
        })
    except Exception as e:
        return handle_generic_error(e)

def get_quality_recommendations(validation_result):
    """Generate recommendations based on voice sample quality"""
    recommendations = []
    
    if validation_result['duration'] < 10:
        recommendations.append("Consider providing a longer voice sample (10-30 seconds) for better quality.")
    
    if validation_result['noise_level'] > 0.05:
        recommendations.append("Try recording in a quieter environment to reduce background noise.")
    
    if validation_result['rms_level'] < 0.02:
        recommendations.append("Speak louder and closer to the microphone for better audio quality.")
    
    return recommendations

# Update the exam session to use cloned voice
@app.route('/api/sessions/<int:session_id>/start', methods=['POST'])
@token_required
def start_exam_session(current_user, session_id):
    try:
        session = ExamSession.query.get_or_404(session_id)
        if session.candidate_id != current_user.id:
            raise AuthenticationError("Unauthorized")
        
        # Check if user has voice profile
        voice_profile = VoiceProfile.query.filter_by(user_id=current_user.id).first()
        use_cloned_voice = voice_profile is not None
        
        session.status = 'in_progress'
        session.start_time = datetime.utcnow()
        session.use_cloned_voice = use_cloned_voice
        db.session.commit()
        
        # Emit session started event with voice preference
        socketio.emit('session_started', {
            'session_id': session_id,
            'use_cloned_voice': use_cloned_voice
        }, room=str(session_id))
        
        return jsonify({
            'message': 'Exam session started',
            'use_cloned_voice': use_cloned_voice
        })
    except Exception as e:
        return handle_generic_error(e)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True) 