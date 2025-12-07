# YouTube Transcript Summarizer

A lightweight proof-of-concept application that downloads YouTube transcripts and generates AI-powered summaries using local Ollama models.

## Features

- Extract transcripts from YouTube videos (no API key required)
- Generate summaries using local Ollama models
- Interactive chat interface to ask questions about the transcript
- Download transcripts as text files
- Model selection dropdown (supports all installed Ollama models)
- Clean, responsive UI

## Prerequisites

1. **Python 3.8+**
2. **Ollama** - [Install Ollama](https://ollama.ai)
3. **Qwen model** (or any other Ollama model)

## Setup

### 1. Install Ollama and pull a model

```bash
# Install Ollama from https://ollama.ai

# Pull the Qwen model (or any other model)
ollama pull qwen2.5:latest

# Start Ollama server
ollama serve
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python app.py
```

The app will start on `http://localhost:5000`

## Usage

1. Paste a YouTube URL into the input field
2. Select your preferred Ollama model from the dropdown
3. Click "Get Transcript" to fetch the transcript
4. Click "Generate Summary" for an AI summary
5. Use the chat interface to ask questions about the video
6. Click "Download Transcript" to save as a text file

## Creating an Executable

To package this as a standalone executable:

```bash
# Install PyInstaller
pip install pyinstaller

# Create executable (single file)
pyinstaller --onefile --add-data "templates:templates" app.py

# Or bundle everything in a folder
pyinstaller --add-data "templates:templates" app.py
```

The executable will be in the `dist/` folder.

Note: You'll still need Ollama running separately.

## Project Structure

```
FinScr1/
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html     # Frontend UI
└── README.md          # This file
```

## Expanding the Application

This is designed to be easily expandable:

### Add new features to backend (`app.py`):
- Add new API endpoints for additional functionality
- Integrate other AI providers (OpenAI, Anthropic, etc.)
- Add database support for saving transcripts/summaries
- Implement user authentication

### Enhance frontend (`templates/index.html`):
- Add more UI controls and settings
- Implement transcript highlighting during playback
- Add export formats (PDF, JSON, etc.)
- Create transcript search functionality

### Add new models:
The model dropdown automatically detects all installed Ollama models. Just install new models with:
```bash
ollama pull <model-name>
```

## Troubleshooting

**"Cannot connect to Ollama"**
- Make sure Ollama is running: `ollama serve`
- Check if Ollama is accessible at `http://localhost:11434`

**"Failed to fetch transcript"**
- The video might not have captions/subtitles available
- Try a different video URL format
- Some videos have restricted transcripts

**Model not appearing in dropdown**
- Restart the Flask app after installing new Ollama models
- Verify model is installed: `ollama list`

## License

MIT
