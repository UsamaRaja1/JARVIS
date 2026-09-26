import subprocess

import cv2

from src.utilz.logger import logger_


def list_cameras():
    """List all available V4L2 camera devices with names and paths."""
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            text=True,
            capture_output=True,
            check=False,  # don't raise on non-zero exit
        )
        output = result.stdout + result.stderr  # combine both
    except FileNotFoundError:
        logger_.error("❌ v4l2-ctl not found. Install it with: sudo apt install v4l-utils")
        return []

    cameras = []
    current_name = None

    for line in output.splitlines():
        if not line.strip():
            continue
        if not line.startswith("\t"):  # camera name line
            current_name = line.strip().rstrip(":")
        elif current_name:  # device path line
            cameras.append((current_name, line.strip()))
    return cameras


def test_camera(device_path):
    """Try to open and read a frame from the given device."""
    cap = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
    if not cap.isOpened():
        return False
    ret, _ = cap.read()
    cap.release()
    return ret


def get_camera_devices():
    cameras = list_cameras()
    if not cameras:
        logger_.error("No cameras found.")
        return []

    logger_.info("\nDetected camera devices:")
    for name, dev in cameras:
        logger_.info(f"  - {name} → {dev}")

    working_devices = []
    logger_.info("\nTesting camera devices...\n")
    for name, dev in cameras:
        if test_camera(dev):
            logger_.info(f"✅ Working: {name} ({dev})")
            working_devices.append(dev)
        else:
            logger_.info(f"❌ Failed:  {name} ({dev})")

    if not working_devices:
        logger_.info("\nNo working camera devices found.")
    else:
        logger_.info("\nWorking devices:", working_devices)

    return working_devices


def get_video_capture(show_video=False):
    devices = get_camera_devices()

    if devices:
        logger_.info(f"\n🎥 Working devices found: {devices}")
        cap = None
        device = None
        # Try to open the first working device
        for device in devices:
            logger_.info(f"Opening video capture: {device}")
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            ret, frame = cap.read()
            if ret:
                logger_.info(f"✅ Successfully opened {device}")
                break
            else:
                cap.release()
                cap = None

        if not show_video:
            return cap

        # Display camera feed
        if cap and cap.isOpened():
            logger_.info("Press 'q' to quit the video window.")
            while True:
                ret, frame = cap.read()
                frame = cv2.flip(frame, 1)
                if not ret:
                    logger_.error("⚠️ Frame capture failed, exiting.")
                    break
                cv2.imshow(f"Camera: {device}", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            cap.release()
            cv2.destroyAllWindows()
        else:
            logger_.error("❌ Could not open any working camera device.")
    else:
        logger_.error("❌ No devices to open.")
    return
