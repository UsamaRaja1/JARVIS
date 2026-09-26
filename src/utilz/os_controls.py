import subprocess

from src.configs import OS_TYPE
from src.utilz.logger import logger_

if OS_TYPE == "windows":
    try:
        from ctypes import POINTER, cast

        import keyboard
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except ImportError:
        logger_.warning("Missing packages for Windows media control. Please install pycaw and keyboard.")


def handle_playback_command(command: str):
    if OS_TYPE == "linux":
        cmds = {"play": ["playerctl", "play"], "pause": ["playerctl", "pause"], "playpause": ["playerctl", "play-pause"], "next": ["playerctl", "next"], "previous": ["playerctl", "previous"]}
        if command in cmds:
            subprocess.run(cmds[command])
        else:
            logger_.warning(f"Unknown Linux playback command: {command}")

    elif OS_TYPE == "windows":
        key_map = {"play": "play/pause", "pause": "play/pause", "playpause": "play/pause", "next": "next track", "previous": "previous track"}
        if command in key_map:
            try:
                keyboard.send(key_map[command])
            except Exception as e:
                logger_.error(f"Failed to send keyboard media key: {e}")
        else:
            logger_.warning(f"Unknown Windows playback command: {command}")
    else:
        logger_.warning(f"Unsupported OS for media control: {OS_TYPE}")


def handle_volume_command(command: str):
    if OS_TYPE == "linux":
        if command == "volume_up":
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"])
        elif command == "volume_down":
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"])
        elif command == "mute":
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        else:
            logger_.warning(f"Unknown Linux volume command: {command}")

    elif OS_TYPE == "windows":
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            current = volume.GetMasterVolumeLevelScalar()
            step = 0.05

            if command == "volume_up":
                volume.SetMasterVolumeLevelScalar(min(current + step, 1.0), None)
            elif command == "volume_down":
                volume.SetMasterVolumeLevelScalar(max(current - step, 0.0), None)
            elif command == "mute":
                volume.SetMute(not volume.GetMute(), None)
            else:
                logger_.warning(f"Unknown Windows volume command: {command}")
        except Exception as e:
            logger_.error(f"Windows volume control failed: {e}")


def handle_media_command(command: str):
    # Unified entry point for media commands
    media_map = {
        "play": handle_playback_command,
        "pause": handle_playback_command,
        "playpause": handle_playback_command,
        "next": handle_playback_command,
        "previous": handle_playback_command,
        "volume_up": handle_volume_command,
        "volume_down": handle_volume_command,
        "mute": handle_volume_command,
    }

    if command in media_map:
        media_map[command](command)
    else:
        logger_.warning(f"Unhandled media command: {command}")
