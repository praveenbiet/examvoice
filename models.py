import torch
from transformers import pipeline
from speechbrain.pretrained import EncoderDecoderASR, Tacotron2
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
import numpy as np

class SpeechRecognition:
    def __init__(self):
        # Initialize SpeechBrain ASR model
        self.asr_model = EncoderDecoderASR.from_hparams(
            source="speechbrain/asr-crdnn-rnnlm-librispeech",
            savedir="pretrained_models/asr-crdnn-rnnlm-librispeech"
        )
    
    def transcribe(self, audio_data):
        # Process audio file and return transcribed text
        transcription = self.asr_model.transcribe_file(audio_data)
        return transcription

class TextToSpeech:
    def __init__(self):
        # Initialize SpeechBrain TTS model
        self.tts_model = Tacotron2.from_hparams(
            source="speechbrain/tts-tacotron2-ljspeech",
            savedir="pretrained_models/tts-tacotron2-ljspeech"
        )
    
    def synthesize(self, text):
        # Convert text to speech and return audio
        mel_output, mel_length, alignment = self.tts_model.encode_text(text)
        waveforms = self.tts_model.decode_batch(mel_output)
        return waveforms

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