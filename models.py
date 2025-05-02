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