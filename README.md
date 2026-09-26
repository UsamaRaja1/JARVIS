# JARVIS

**Voice, Vision & Automation**

JARVIS is an experimental, Linux-focused personal assistant that combines voice
interaction, local desktop automation, face and voice recognition, optional LLM
providers, and optional Arduino/Blynk hardware control.

> [!WARNING]
> Jarvis can control your keyboard, desktop, files, and connected hardware. Review
> the code and configuration before running it. Do not expose its MCP server or
> hardware endpoints to untrusted users.

## Features

- Wake-word and conversational voice interaction
- OpenAI, OpenRouter, Groq, and Gemini provider routing
- Face detection and recognition with locally generated encodings
- Optional voice recognition using pyannote
- Linux desktop, media, brightness, and application controls
- Optional Arduino and Blynk smart-device control
- A stdio Model Context Protocol (MCP) server

Most hardware and recognition features are optional. The project is currently
developed and tested primarily on Ubuntu with Python 3.11.

## Quick start

### 1. Install system packages

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y build-essential cmake espeak-ng ffmpeg libasound2-dev \
  libboost-all-dev libopenblas-dev liblapack-dev libsndfile1 portaudio19-dev \
  python3.11 python3.11-dev python3.11-venv playerctl wmctrl xdotool brightnessctl
```

Some desktop tools may require additional permissions. Camera, microphone, and
Arduino features require the corresponding hardware.

### 2. Create the Python environment

```bash
git clone https://github.com/UsamaRaja1/JARVIS.git
cd JARVIS
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The full voice/vision stack is large and includes PyTorch, MediaPipe, dlib, and
audio-system dependencies. Installation can take several minutes.

### 3. Configure providers

```bash
cp .env.template .env
```

Edit `.env` and provide at least one supported LLM API key. Never commit `.env`.
Hardware, Notion, Hugging Face, and computer-unlock settings are optional.

### 4. Run Jarvis

From the repository root:

```bash
PYTHONPATH=. python -m src.jarvis_v2
```

For long-running Linux deployments using Conda and PM2:

```bash
./scripts/deploy.sh start
```

## Face-recognition setup

The repository includes `src/data/images-samples/AlexExample.jpg`, a synthetic
person generated solely for demonstrating the expected input. It does not depict
a known or intentionally identifiable real person.

To enroll someone:

1. Obtain their consent before processing biometric data.
2. Place one clear, front-facing JPG or PNG photo in
   `src/data/images-samples/`.
3. Name the file after the display name, such as `JaneDoe.jpg`.
4. Start Jarvis. The encoding is generated locally in
   `src/data/images-encodings/`.

Personal samples and generated encodings are ignored by Git. Do not commit them.

## User configuration

On first import, Jarvis copies these committed templates into private runtime files:

- `src/data/users.example.json` → `src/data/users.json`
- `src/data/shared_data.example.json` → `src/data/shared_data.json`

Edit `users.json` for local workspace preferences. Runtime JSON files are ignored
by Git, while the `.example.json` templates document the supported structure.

## MCP server

Start the stdio MCP server with:

```bash
PYTHONPATH=. python -m src.mcp.server
```

Tools are registered in `src/mcp/tool_impl.py`. Desktop and device-control tools
perform real actions on the host, so only connect trusted MCP clients.

## Development

```bash
python -m pip install -e '.[dev]'
pre-commit install
ruff check --no-fix .
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance and
[SECURITY.md](SECURITY.md) for the security policy.

## Privacy

Face images, biometric encodings, voice samples, logs, generated audio, temporary
files, local user state, and API credentials must remain local. The `.gitignore`
contains rules for these artifacts, but contributors are responsible for reviewing
staged changes before every commit.

## License

Licensed under the [MIT License](LICENSE).
