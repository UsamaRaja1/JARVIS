import base64
import os
from datetime import UTC, datetime

import cv2
import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

from src.configs import BOT_NAME, USER_NAME
from src.llm.ai_response_handler import ConversationAI
from src.utilz.logger import logger_

load_dotenv()


class ChatAI:
    def __init__(self, bot_name, api_key=None, model=None):
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.messages = []
        self.bot_name = bot_name
        self._initialize_chat()
        self.ai = ConversationAI(model or os.getenv("LLM_OPENROUTER_MODEL") or os.getenv("LLM_GROQ_MODEL", "llama-3.3-70b-versatile"))

    def _initialize_chat(self, clear_chat=True):
        """Initializes the chat with a system message."""
        system_message = (
            f"You are {self.bot_name}, a highly intelligent and efficient AI assistant with a professional, witty, and polite demeanor. "
            f"Respond concisely and helpfully, addressing the user as '{USER_NAME}'. Your primary goals are to execute commands accurately, "
            f"provide insightful answers, and anticipate the user's needs. Avoid unnecessary emotion or personal opinions, focusing instead on precision and intelligence."
            f"General information:\nTime and Date: {datetime.now(UTC).isoformat()}"
        )
        if clear_chat:
            self.messages = []
            self.messages.append({"role": "system", "content": system_message})
        elif self.messages:
            self.messages[0]["content"] = system_message
        else:
            self.messages.append({"role": "system", "content": system_message})

    async def chat(self, query: str | None = None, image: np.array = None, image_path: str | None = None, messages: list[dict] | None = None, task: str | None = None) -> dict:
        """Processes an image with a query and returns the assistant's response."""
        try:
            if messages:
                response = self.ai.chat(messages, task=task)
                return response

            if len(self.messages) > 10:
                self.messages = [self.messages[0], *self.messages[-10:]]

            base64_image = None
            if image_path:
                base64_image = self._encode_image(image_path)
            elif image is not None:
                base64_image = self._encode_image_from_array(image)

            if base64_image is not None:
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": query,
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                )
            else:
                self.messages.append({"role": "user", "content": query})

            response = self.ai.chat(self.messages, task=task)
            self.messages.append({"role": "assistant", "content": response["content"]})

            return response
        except Exception as e:
            logger_.error(f"Chat error: {e!s}")
            return {"error": str(e)}

    def _encode_image(self, image_path):
        """Encodes an image file as a base64 string."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            logger_.error(f"Error encoding image from path: {e!s}")
            raise

    def _encode_image_from_array(self, image):
        """Encodes an image array as a base64 string."""
        try:
            _, buffer = cv2.imencode(".jpg", image)  # Change '.jpg' to '.png' if needed
            return base64.b64encode(buffer).decode("utf-8")
        except Exception as e:
            logger_.error(f"Error encoding image from array: {e!s}")
            raise


chat_ai = ChatAI(BOT_NAME)

if __name__ == "__main__":
    # Text-based query
    print(chat_ai.chat("Hello, how can you assist me today?"))

    # Image-based query
    image_path = "../../docs/images/pose_landmarks_index.png"
    response = chat_ai.chat("What do you see in this image?", image_path=image_path)
    print(response)
