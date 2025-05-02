from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from models import SpeechRecognition, TextToSpeech, AnswerEvaluator, VoiceRecognition, User, Exam, Question, ExamSession, ExamResponse, VoiceProfile
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

app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
CORS(app)
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
    session = ExamSession.query.get_or_404(session_id)
    if current_user.role not in ['admin', 'examiner'] and session.candidate_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403
    
    exam = Exam.query.get(session.exam_id)
    total_allowed_time = exam.duration_minutes + (session.extended_minutes or 0)
    time_elapsed = (datetime.utcnow() - session.start_time).total_seconds() / 60
    time_remaining = total_allowed_time - time_elapsed
    
    return jsonify({
        'time_elapsed': time_elapsed,
        'time_remaining': max(0, time_remaining),
        'total_allowed_time': total_allowed_time,
        'extended_minutes': session.extended_minutes or 0,
        'warning_threshold': 5  # minutes before warning
    })

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 