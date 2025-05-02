# Voice-Based Exam System

A modern web application for conducting voice-based exams with automatic speech recognition and voice verification.

## Project Structure

```
examvoice/
├── backend/
│   ├── app.py              # Flask backend server
│   ├── models.py           # ML models and business logic
│   └── requirements.txt    # Python dependencies
├── frontend/
│   ├── public/             # Static files
│   ├── src/
│   │   ├── components/     # Reusable React components
│   │   ├── pages/         # Page components
│   │   ├── App.js         # Main application component
│   │   └── index.js       # Entry point
│   └── package.json       # Node.js dependencies
└── README.md              # Project documentation
```

## Features

- Voice-based exam interface
- Automatic speech recognition using NVIDIA Parakeet TDT 0.6B V2
- Voice verification for candidate identification
- Real-time audio visualization
- Session management and resumption
- Modern, responsive UI with Material-UI

## Setup Instructions

### Backend Setup

1. Create a virtual environment:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the backend server:
```bash
python app.py
```

### Frontend Setup

1. Install Node.js dependencies:
```bash
cd frontend
npm install
```

2. Start the development server:
```bash
npm start
```

## Usage

1. Open the application in your web browser (default: http://localhost:3000)
2. Enter your candidate ID and record your voice sample
3. Complete the voice verification process
4. Answer exam questions by speaking into the microphone
5. Review feedback and move to the next question
6. The exam can be resumed from where you left off

## Technologies Used

- Frontend:
  - React.js
  - Material-UI
  - Web Audio API
  - React Router

- Backend:
  - Flask
  - NVIDIA NeMo (ASR)
  - SpeechBrain (Voice Recognition)
  - Sentence Transformers (Answer Evaluation)

## License

MIT License 