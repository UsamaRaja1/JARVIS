import re
import webbrowser
from urllib.parse import urlparse

from pytube import Search

from src.utilz.logger import logger_


def search_and_play(query, assistant):
    # Search on YouTube
    match = re.search(r"(?:search|play) (.+?) on (\w+)", query, re.IGNORECASE)
    if match:
        text, platform = match.groups()

        if platform == "youtube":
            logger_.info(f"Searching for '{text}' on YouTube...")
            assistant.say(f"Searching for '{text}' on YouTube...")
            search_results = Search(query).results

            if not search_results:
                logger_.info("No results found.")
                return

            # Get the first video result
            video = search_results[0]
            video_url = video.watch_url
            logger_.info(f"Playing video: {video.title}")
            logger_.info(f"URL: {video_url}")

            # Open the video in the web browser
            webbrowser.open(video_url)
        else:
            logger_.info(f"Searching for {text} on {platform}...")
            assistant.say(f"Searching for {text} on {platform}...")
            search_query(query)


def search_query(query, search_engine="https://www.google.com/search?q="):
    # Encode the query to handle spaces and special characters
    encoded_query = query.replace(" ", "+")  # Use urllib.parse.quote_plus for more robust encoding if needed
    # Construct the search URL
    search_url = f"{search_engine}{encoded_query}"
    # Open the search URL in the default web browser
    webbrowser.open(search_url)


def resolve_website_url(query: str) -> tuple[str, str]:
    text = query.strip()
    text = re.sub(r"^(?:open|launch|start)\s+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+(?:website|site|webpage)$", "", text, flags=re.IGNORECASE).strip()

    if not text:
        return "", ""

    if text.startswith(("http://", "https://")):
        parsed = urlparse(text)
        host = parsed.netloc or parsed.path
        return text, host

    host = re.sub(r"^www\.", "", text, flags=re.IGNORECASE).strip().strip("/")
    host = host.split()[0]
    if "." not in host:
        host = f"{host}.com"

    url = f"https://www.{host}" if not text.lower().startswith("www.") else f"https://{text}"
    return url, host


def extract_website(command):
    _url, website = resolve_website_url(command)
    return website
