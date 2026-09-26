# Base image
FROM python:3.11-slim

# Set environment variables to avoid prompts during install
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-dev \
    build-essential \
    portaudio19-dev libasound2-dev ffmpeg \
    libffi-dev libssl-dev libsndfile1 \
    git curl wget unzip \
    cmake \
    libboost-all-dev \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install Python dependencies
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Default command to run Jarvis
CMD ["python", "-m", "src.jarvis_v2"]
