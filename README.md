# JARVIS

**Voice, Vision & Automation**

JARVIS is an experimental, cross-platform personal assistant that combines voice
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
- Desktop, media, volume, brightness, and application controls
- Optional Arduino and Blynk smart-device control
- A stdio Model Context Protocol (MCP) server

Most hardware and recognition features are optional. The project is developed
primarily on Ubuntu with Python 3.11. Windows supports the core voice, vision,
media-key, volume, and serial features; Linux-only desktop features are identified
below.

## Quick start

### Ubuntu/Debian

Clone the repository and run the Linux setup script:

```bash
git clone https://github.com/UsamaRaja1/JARVIS.git
cd JARVIS
./scripts/setup.sh
source .venv/bin/activate
```

The script installs the required Debian packages, creates or reuses `.venv`,
installs the Python dependencies, and creates `.env` from `.env.template` when
needed.

### Windows

Install these prerequisites first:

- [Python 3.11](https://www.python.org/downloads/) with the Python launcher
- [Git for Windows](https://git-scm.com/download/win)
- Microsoft C++ Build Tools with the **Desktop development with C++** workload
- CMake and FFmpeg available on `PATH`

Then open PowerShell or Command Prompt:

```powershell
git clone https://github.com/UsamaRaja1/JARVIS.git
cd JARVIS
scripts\setup-windows.bat
```

Alternatively, invoke the PowerShell installer directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1
```

Activate the environment with `.\.venv\Scripts\Activate.ps1`, or run JARVIS
directly with `.\.venv\Scripts\python.exe -m src.jarvis_v2`.

### Configure providers

The setup scripts create `.env` from `.env.template` only when it does not already
exist. Edit `.env` and provide at least one supported LLM API key. Never commit
`.env`. Hardware, Notion, Hugging Face, and computer-unlock settings are optional.

### Run JARVIS

From the repository root:

```bash
PYTHONPATH=. python -m src.jarvis_v2
```

For long-running Linux deployments using Conda and PM2:

```bash
./scripts/deploy.sh start
```

### Current platform limitations

- Window enumeration, window focusing, virtual-desktop switching, and brightness
  control currently rely on Linux utilities such as `wmctrl`, `xdotool`, and
  `brightnessctl`.
- Camera and microphone device selection can vary by Windows driver.
- `face-recognition` may require CMake and the Microsoft C++ Build Tools to build
  its `dlib` dependency on Windows.
- Some optional speech and vision models are downloaded on first use and can be
  several gigabytes.

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
