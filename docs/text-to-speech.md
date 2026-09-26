# Text-to-speech

Jarvis uses the operating system's speech engine to synthesize responses. The
default engine depends on the platform:

| Platform | Engine | Status |
| --- | --- | --- |
| Linux | eSpeak | Primary and tested path |
| Windows | `pyttsx3` | Supported by the Python implementation |
| macOS | Not currently configured | Contributions welcome |

## Linux setup

Install eSpeak NG on Ubuntu or Debian:

```bash
sudo apt update
sudo apt install espeak-ng
```

Confirm that the executable and voices are available:

```bash
espeak --version
espeak --voices
espeak "Jarvis text-to-speech test"
```

Jarvis writes synthesized speech to `src/temp/output.wav` and plays it through
`simpleaudio`. The temporary audio file is ignored by Git.

## Windows setup

The Windows dependency is installed automatically from `requirements.txt` using
its platform marker. To inspect voices from Python:

```python
import pyttsx3

engine = pyttsx3.init()
for voice in engine.getProperty("voices"):
    print(voice.id, voice.name)
```

## Festival

Festival support is retained only as an optional fallback for the legacy `say()`
helper. It is not required for the main `TTS` and `TTS2` classes, and Jarvis no
longer requires the unmaintained `pyfestival` package during normal installation.

## Troubleshooting

- `espeak: command not found`: install `espeak-ng` and ensure `espeak` is on
  `PATH`.
- No audio output: verify the system output device and test a WAV file with
  another player.
- `simpleaudio` fails to install: install `libasound2-dev` and Python development
  headers, then reinstall the Python requirements.
- Speech is generated but sounds incorrect: list installed voices with
  `espeak --voices` and test the desired language directly with eSpeak first.
