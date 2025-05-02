from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from models import SpeechRecognition, TextToSpeech, AnswerEvaluator, VoiceRecognition
import os
from datetime import datetime
import io

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

@app.route('/start_exam', methods=['POST'])
def start_exam():
    try:
        candidate_id = request.form.get('candidate_id')
        voice_sample = request.files.get('voice_sample')
        
        if not candidate_id or not voice_sample:
            return jsonify({'error': 'Missing required data'}), 400
        
        # Save voice sample
        voice_path = f"voice_profiles/{candidate_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        os.makedirs('voice_profiles', exist_ok=True)
        voice_sample.save(voice_path)
        
        # Register voice profile
        voice_recognition.register_voice(candidate_id, voice_path)
        
        # Create exam session
        session = ExamSession(candidate_id, voice_path)
        active_sessions[candidate_id] = session
        
        return jsonify({
            'status': 'success',
            'message': 'Exam started',
            'session_id': candidate_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 