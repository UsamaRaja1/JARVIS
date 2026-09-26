import glob
import os
import pickle
import re
import time
from datetime import datetime

import cv2
import face_recognition as fr
import requests

from src.configs import IMAGE_ENCODING_DIR
from src.modules.user_manager import UserManager
from src.utilz.logger import logger_

user_manager = UserManager()


def open_video_capture(devices=None):
    if devices is None:
        # devices = ["/dev/video5", 0]
        devices = glob.glob("/dev/video*")
        devices.sort(reverse=False)
        # devices = [device for device in devices if device not in ["/dev/video0", "/dev/video1"]]
        # devices.extend([2,1,0])
        logger_.info(devices)

    for device in devices:
        try:
            cap = cv2.VideoCapture(device)
            if cap.isOpened():
                logger_.info(f"Opened video capture device: {device}")
                ret, _frame = cap.read()
                time.sleep(1)
                if ret:
                    return cap
        except cv2.error as e:
            logger_.error(f"Error opening {device}: {e}")

    logger_.error("None of the specified devices could be opened.")
    return None


def load_images(path, resize=1):
    supported_extensions = {".jpg", ".jpeg", ".png"}
    images_path = sorted(
        image_path
        for image_path in glob.glob(os.path.join(path, "*"))
        if os.path.splitext(image_path)[1].lower() in supported_extensions
    )
    images = []
    names = []
    for image_path in images_path:
        name = os.path.basename(image_path).split(".")[0]
        image = cv2.imread(image_path)
        if image is None:
            logger_.warning(f"Skipping unreadable image: {image_path}")
            continue
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if resize < 1:
            width, height, _ = image.shape
            image = cv2.resize(image, (int(width * resize), int(height * resize)))

        images.append(image)
        names.append(name)

    logger_.info(f"Images loaded from: {path}")

    return {"images": images, "names": names}


def encode_images(images_data, encodings_dir=None):
    encoded_images = []
    names = images_data["names"]
    encodings_dir = encodings_dir if encodings_dir else IMAGE_ENCODING_DIR

    if not os.path.exists(encodings_dir):
        os.makedirs(encodings_dir)

    logger_.info(f"Loading (or generating) face encodings for {len(names)} images... ")
    for i, image in enumerate(images_data["images"]):
        file_path = os.path.join(encodings_dir, f"{names[i]}.pkl")
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                encodings = pickle.load(f)
            encoded_images.append(encodings)
        else:
            detected_encodings = fr.face_encodings(image)
            if not detected_encodings:
                logger_.warning(f'No face detected in sample "{names[i]}"; skipping it.')
                continue
            encoded_image = detected_encodings[0]
            # encoded_images.append({"face_encoding": encoded_image, "name": image["name"]})
            encoded_images.append(encoded_image)
            with open(file_path, "wb") as f:
                pickle.dump(encoded_image, f)

    return encoded_images


def process_input(command):
    # Remove trailing question marks or punctuation marks
    cleaned_command = re.sub(r"[?!.]", "", command).strip().lower()
    return cleaned_command


def read_responses_from_file(file_path):
    responses_dict = {}
    with open(file_path) as file:
        for line in file:
            pattern, *responses = line.strip().split("|")
            pattern = process_input(pattern)
            responses_dict[pattern] = responses
    return responses_dict


def map_value(x, in_min, in_max, out_min, out_max):
    """
    Maps a number from one range to another.

    Parameters:
    - x: The input value.
    - in_min: The lower bound of the input range.
    - in_max: The upper bound of the input range.
    - out_min: The lower bound of the output range.
    - out_max: The upper bound of the output range.

    Returns:
    - The mapped value in the output range.
    """
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def get_weather(city):
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return "Weather is unavailable because OPENWEATHER_API_KEY is not configured."
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": api_key, "units": "metric"}
    response = requests.get(base_url, params=params)
    weather_data = response.json()

    if weather_data["cod"] == 200:
        temperature = weather_data["main"]["temp"]
        weather_desc = weather_data["weather"][0]["description"]
        return f"The current temperature in {city} is {temperature:.1f}°C with {weather_desc}."
    else:
        # return "Sorry, I could not retrieve weather Sorry, I could not retrieve weather information for that city."
        return "Sorry, I'm having trouble connecting to the server, just look out the window"


def check(words: list, text: str):
    """
    Checks if all the words exist in the command
    :param words: list of words to check
    :param text: text string
    :return: bool
    """
    if words:
        return all(word in text for word in words)
    return False


def extract_number(command):
    # Regular expression to match a number, possibly with ordinal suffixes like "1st", "2nd", "3rd", etc.
    match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\b", command)
    if match:
        return int(match.group(1))  # Extract and convert the number to an integer
    else:
        ordinal_map = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
            # Add more as needed
        }
        match = re.search(r"\b(\d+|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", command.lower())
        if match:
            # Check if the match is a number or an ordinal word
            match_value = match.group(1)
            if match_value.isdigit():
                return int(match_value)
            elif match_value in ordinal_map:
                return ordinal_map[match_value]
        return None


def get_greetings():
    """Greet according to the time"""
    current_datetime = datetime.now()
    hour = current_datetime.now().hour
    if (hour >= 6) and (hour < 12):
        greeting = "Good Morning"
    elif (hour >= 12) and (hour < 16):
        greeting = "Good Afternoon"
    elif (hour >= 16) and (hour < 19):
        greeting = "Good Evening"
    else:
        greeting = "Hi"
    return greeting


def set_brightness(command: str = "", brightness: int | None = None):
    if command:
        match = re.search(r"(?:set|increase|decrease)?\s*brightness level(?:\s*(?:to|by))?\s*(\d{1,3})\s*%?", command, re.IGNORECASE)

        if match:
            brightness = int(match.group(1))

    if brightness:
        os.system(f"brightnessctl set {brightness}%")


def setup_workspace(username):
    user = user_manager.get_user(username)
    if user:
        brightness = user["workspace"]["brightness"]
        set_brightness(brightness=brightness)
    else:
        logger_.info(f'User "{username}" not found.')
