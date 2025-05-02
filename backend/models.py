import torch
from transformers import pipeline
import nemo.collections.asr as nemo_asr
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
import numpy as np
import soundfile as sf
from dia.model import Dia
import os
from datetime import datetime
import torchaudio
from speechbrain.pretrained import SpeakerRecognition
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'examiner', 'candidate'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    exams_created = db.relationship('Exam', backref='creator', lazy=True)
    exam_sessions = db.relationship('ExamSession', backref='candidate', lazy=True)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Exam(db.Model):
    __tablename__ = 'exams'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    passing_score = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    questions = db.relationship('Question', backref='exam', lazy=True)
    sessions = db.relationship('ExamSession', backref='exam', lazy=True)
    
    def __repr__(self):
        return f'<Exam {self.title}>'

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    max_score = db.Column(db.Float, nullable=False)
    order = db.Column(db.Integer, nullable=False)
    
    # Relationships
    responses = db.relationship('ExamResponse', backref='question', lazy=True)
    
    def __repr__(self):
        return f'<Question {self.id}>'

class ExamSession(db.Model):
    __tablename__ = 'exam_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='in_progress')  # 'in_progress', 'completed', 'abandoned'
    total_score = db.Column(db.Float, default=0.0)
    
    # Relationships
    responses = db.relationship('ExamResponse', backref='session', lazy=True)
    
    def __repr__(self):
        return f'<ExamSession {self.id}>'

class ExamResponse(db.Model):
    __tablename__ = 'exam_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('exam_sessions.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    audio_path = db.Column(db.String(500), nullable=False)
    transcribed_text = db.Column(db.Text)
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ExamResponse {self.id}>'

class VoiceProfile(db.Model):
    __tablename__ = 'voice_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    voice_sample_path = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<VoiceProfile {self.id}>'

class VoiceRecognition:
    def __init__(self):
        # Initialize speaker recognition model
        self.speaker_model = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="pretrained_models/spkrec-ecapa-voxceleb"
        )
        self.voice_profiles = {}  # Store voice embeddings for each user
    
    def extract_voice_features(self, audio_path):
        # Extract voice features from audio
        signal, fs = torchaudio.load(audio_path)
        embeddings = self.speaker_model.encode_batch(signal)
        return embeddings.squeeze(0)
    
    def register_voice(self, user_id, audio_path):
        # Register a new voice profile
        embeddings = self.extract_voice_features(audio_path)
        self.voice_profiles[user_id] = embeddings
        return True
    
    def verify_speaker(self, audio_path, user_id):
        # Verify if the speaker matches the registered profile
        if user_id not in self.voice_profiles:
            return False
        
        test_embeddings = self.extract_voice_features(audio_path)
        similarity = self.speaker_model.similarity(
            test_embeddings, 
            self.voice_profiles[user_id]
        )
        return similarity > 0.7  # Threshold for verification

class SpeechRecognition:
    def __init__(self):
        # Initialize NVIDIA Parakeet TDT 0.6B V2 model
        self.asr_model = nemo_asr.models.ASRModel.from_pretrained(
            model_name="nvidia/parakeet-tdt-0.6b-v2"
        )
    
    def transcribe(self, audio_path):
        try:
            # Process audio file and return transcribed text with timestamps
            output = self.asr_model.transcribe([audio_path], timestamps=True)
            
            # Get the transcribed text
            transcription = output[0].text
            
            # Get word-level timestamps for better accuracy tracking
            word_timestamps = output[0].timestamp['word']
            
            # Log the transcription and timestamps for debugging
            print(f"Transcription: {transcription}")
            print("Word timestamps:")
            for stamp in word_timestamps:
                print(f"{stamp['start']}s - {stamp['end']}s : {stamp['word']}")
            
            return transcription
        except Exception as e:
            print(f"Error in speech recognition: {str(e)}")
            return ""

class TextToSpeech:
    def __init__(self):
        # Initialize Dia TTS model
        self.tts_model = Dia.from_pretrained("nari-labs/Dia-1.6B")
        self.output_dir = "tts_output"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def synthesize(self, text):
        try:
            # Format text for Dia model
            formatted_text = f"[S1] {text}"
            
            # Generate speech
            output = self.tts_model.generate(formatted_text)
            
            # Save the audio file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = os.path.join(self.output_dir, f"feedback_{timestamp}.wav")
            sf.write(output_path, output, 44100)
            
            return output_path
        except Exception as e:
            print(f"Error in TTS synthesis: {str(e)}")
            # Fallback to simple text if TTS fails
            return text

class AnswerEvaluator:
    def __init__(self):
        # Initialize sentence transformer for semantic similarity
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    def evaluate_similarity(self, candidate_answer, correct_answer):
        # Encode both answers
        candidate_embedding = self.model.encode(candidate_answer)
        correct_embedding = self.model.encode(correct_answer)
        
        # Calculate cosine similarity
        similarity = 1 - cosine(candidate_embedding, correct_embedding)
        return float(similarity) 