from flask import Flask, render_template, request, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from models import SpeechRecognition, TextToSpeech, AnswerEvaluator
import os
from datetime import datetime
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exam.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# Initialize ML models
speech_recognition = SpeechRecognition()
text_to_speech = TextToSpeech()
answer_evaluator = AnswerEvaluator()

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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_exam', methods=['POST'])
def start_exam():
    candidate_id = request.form.get('candidate_id')
    session['candidate_id'] = candidate_id
    return jsonify({'status': 'success', 'message': 'Exam started'})

@app.route('/get_question', methods=['GET'])
def get_question():
    question = Question.query.first()  # For demo, get first question
    return jsonify({
        'question_id': question.id,
        'question_text': question.question_text,
        'voice_instruction': question.voice_instruction
    })

@app.route('/process_answer', methods=['POST'])
def process_answer():
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        question_id = request.form.get('question_id')
        
        if not audio_file or not question_id:
            return jsonify({'error': 'Missing required data'}), 400

        # Save audio file
        audio_path = f"uploads/{session['candidate_id']}_{question_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
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
        
        # Save result
        result = ExamResult(
            candidate_id=session['candidate_id'],
            question_id=question_id,
            candidate_answer=candidate_answer,
            similarity_score=similarity_score,
            audio_path=audio_path
        )
        db.session.add(result)
        db.session.commit()
        
        # Generate feedback
        feedback = text_to_speech.synthesize(
            f"Your answer was {similarity_score*100:.2f}% similar to the correct answer."
        )
        
        return jsonify({
            'status': 'success',
            'similarity_score': similarity_score,
            'feedback': feedback,
            'transcribed_text': candidate_answer
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_audio/<int:result_id>', methods=['GET'])
def get_audio(result_id):
    result = ExamResult.query.get_or_404(result_id)
    if not result.audio_path or not os.path.exists(result.audio_path):
        return jsonify({'error': 'Audio file not found'}), 404
    
    return send_file(
        result.audio_path,
        mimetype='audio/wav',
        as_attachment=True,
        download_name=f'answer_{result_id}.wav'
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 