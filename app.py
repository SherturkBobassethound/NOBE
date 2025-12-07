from flask import Flask, render_template, request, jsonify, send_file, Response, stream_with_context
from youtube_transcript_api import YouTubeTranscriptApi
import requests
import re
import io
import json
import subprocess
import sys

app = Flask(__name__)

# Store transcript in memory (for chat context)
current_transcript = {"text": "", "video_id": ""}

# Store update status
update_status = {"has_updates": False, "updates": []}

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def check_for_updates():
    """Check for package updates on startup"""
    global update_status
    try:
        print("Checking for package updates...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'list', '--outdated', '--format=json'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            outdated = json.loads(result.stdout)
            # Filter for our key packages
            key_packages = ['flask', 'youtube-transcript-api', 'requests']
            updates = [pkg for pkg in outdated if pkg['name'].lower() in key_packages]

            if updates:
                update_status['has_updates'] = True
                update_status['updates'] = updates
                print(f"Found {len(updates)} package updates available:")
                for pkg in updates:
                    print(f"  - {pkg['name']}: {pkg['version']} → {pkg['latest_version']}")
            else:
                print("All packages are up to date!")
    except Exception as e:
        print(f"Could not check for updates: {e}")

def get_ollama_models():
    """Get list of available Ollama models"""
    try:
        response = requests.get('http://localhost:11434/api/tags')
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [model['name'] for model in models]
        return ['qwen2.5:latest']
    except:
        return ['qwen2.5:latest']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/models', methods=['GET'])
def get_models():
    """Return available Ollama models"""
    models = get_ollama_models()
    return jsonify({'models': models})

@app.route('/api/updates', methods=['GET'])
def get_updates():
    """Return update status"""
    return jsonify(update_status)

@app.route('/api/update-packages', methods=['POST'])
def update_packages():
    """Update outdated packages"""
    global update_status
    try:
        packages_to_update = [pkg['name'] for pkg in update_status.get('updates', [])]

        if not packages_to_update:
            return jsonify({'success': False, 'message': 'No packages to update'})

        # Update packages
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '--upgrade'] + packages_to_update,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            # Refresh update status
            update_status['has_updates'] = False
            update_status['updates'] = []
            return jsonify({
                'success': True,
                'message': f'Successfully updated {len(packages_to_update)} package(s). Please restart the app.'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Update failed: {result.stderr}'
            }), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/transcript', methods=['POST'])
def get_transcript():
    """Fetch YouTube transcript"""
    global current_transcript

    data = request.json
    url = data.get('url', '')

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        # Use new API (v1.2.3+)
        api = YouTubeTranscriptApi()
        result = api.fetch(video_id)

        # Extract text from snippets
        transcript_text = ' '.join([snippet.text for snippet in result.snippets])

        # Store for chat context
        current_transcript = {
            "text": transcript_text,
            "video_id": video_id,
            "language": result.language,
            "language_code": result.language_code
        }

        return jsonify({
            'success': True,
            'transcript': transcript_text,
            'video_id': video_id
        })
    except Exception as e:
        return jsonify({'error': f'Failed to fetch transcript: {str(e)}'}), 400

@app.route('/api/summarize', methods=['POST'])
def summarize():
    """Generate summary using Ollama with streaming"""
    data = request.json
    transcript = data.get('transcript', '')
    model = data.get('model', 'qwen2.5:latest')
    prompt_template = data.get('prompt_template', '')

    if not transcript:
        return jsonify({'error': 'No transcript provided'}), 400

    # Handle very long transcripts (>100k characters)
    transcript_length = len(transcript)
    if transcript_length > 100000:
        # Truncate to last 80k characters to fit in context
        transcript = "...[transcript truncated]...\n\n" + transcript[-80000:]

    # Use custom prompt template if provided, otherwise use default
    if prompt_template and '{transcript}' in prompt_template:
        prompt = prompt_template.replace('{transcript}', transcript)
    else:
        prompt = f"""Please provide a concise summary of the following transcript:

{transcript}

Summary:"""

    def generate():
        try:
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': model,
                    'prompt': prompt,
                    'stream': True
                },
                stream=True,
                timeout=None  # No timeout - streaming handles this
            )

            if response.status_code == 200:
                has_sent_thinking_start = False
                thinking_mode = False

                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)

                        # Check for thinking field (deepseek-r1 style)
                        if 'thinking' in chunk and chunk['thinking']:
                            if not has_sent_thinking_start:
                                yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"
                                has_sent_thinking_start = True
                                thinking_mode = True

                            yield f"data: {json.dumps({'type': 'thinking', 'content': chunk['thinking']})}\n\n"

                        # Regular response
                        if 'response' in chunk and chunk['response']:
                            # If we were in thinking mode, end it now
                            if thinking_mode:
                                yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"
                                thinking_mode = False

                            yield f"data: {json.dumps({'type': 'token', 'content': chunk['response']})}\n\n"

                        if chunk.get('done', False):
                            if thinking_mode:
                                yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            break
            else:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Ollama request failed'})}\n\n"
        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Cannot connect to Ollama'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat with Ollama with streaming (works with or without transcript)"""
    global current_transcript

    data = request.json
    message = data.get('message', '')
    model = data.get('model', 'qwen2.5:latest')
    transcript_prompt_template = data.get('transcript_prompt_template', '')
    general_prompt_template = data.get('general_prompt_template', '')

    if not message:
        return jsonify({'error': 'No message provided'}), 400

    # Check if we have a transcript - if yes, use transcript mode
    if current_transcript.get('text'):
        # Use custom transcript prompt template if provided
        if transcript_prompt_template and '{transcript}' in transcript_prompt_template and '{message}' in transcript_prompt_template:
            prompt = transcript_prompt_template.replace('{transcript}', current_transcript['text']).replace('{message}', message)
        else:
            prompt = f"""You are a helpful assistant analyzing a YouTube video transcript. Here is the transcript:

{current_transcript['text']}

User question: {message}

Answer:"""
    else:
        # General chat mode without transcript
        # Use custom general prompt template if provided
        if general_prompt_template and '{message}' in general_prompt_template:
            prompt = general_prompt_template.replace('{message}', message)
        else:
            prompt = f"""You are a helpful AI assistant. Please answer the following question:

{message}

Answer:"""

    def generate():
        try:
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    'model': model,
                    'prompt': prompt,
                    'stream': True
                },
                stream=True,
                timeout=None  # No timeout - streaming handles this
            )

            if response.status_code == 200:
                has_sent_thinking_start = False
                thinking_mode = False

                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)

                        # Check for thinking field (deepseek-r1 style)
                        if 'thinking' in chunk and chunk['thinking']:
                            if not has_sent_thinking_start:
                                yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"
                                has_sent_thinking_start = True
                                thinking_mode = True

                            yield f"data: {json.dumps({'type': 'thinking', 'content': chunk['thinking']})}\n\n"

                        # Regular response
                        if 'response' in chunk and chunk['response']:
                            # If we were in thinking mode, end it now
                            if thinking_mode:
                                yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"
                                thinking_mode = False

                            yield f"data: {json.dumps({'type': 'token', 'content': chunk['response']})}\n\n"

                        if chunk.get('done', False):
                            if thinking_mode:
                                yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            break
            else:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Ollama request failed'})}\n\n"
        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Cannot connect to Ollama'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/download', methods=['GET'])
def download_transcript():
    """Download transcript as text file"""
    global current_transcript

    if not current_transcript.get('text'):
        return jsonify({'error': 'No transcript available'}), 400

    # Create text file in memory
    transcript_text = current_transcript['text']
    video_id = current_transcript.get('video_id', 'transcript')

    buffer = io.BytesIO()
    buffer.write(transcript_text.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'transcript_{video_id}.txt',
        mimetype='text/plain'
    )

if __name__ == '__main__':
    print("Starting YouTube Transcript Summarizer...")
    print("Make sure Ollama is running: ollama serve")
    check_for_updates()
    app.run(debug=True, port=5000)
