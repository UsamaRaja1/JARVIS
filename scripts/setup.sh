#!/bin/bash
# ==========================================
# Jarvis Project Setup Script
# Python 3.11 + Virtual Environment (Linux)
# ==========================================

# Stop on errors, undefined variables, and failed pipelines.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# --- CONFIGURATION ---
PYTHON_VERSION=3.11
VENV_DIR=".venv"
REQUIREMENTS_FILE="requirements.txt"
PROJECT_NAME="Jarvis"

echo "Setting up $PROJECT_NAME environment..."

# --- CHECK PYTHON VERSION ---
if ! command -v python$PYTHON_VERSION &>/dev/null; then
  echo "Python $PYTHON_VERSION is not installed. Please install it first."
  exit 1
fi

# --- SYSTEM TOOLS (Debian/Ubuntu) ---
# Install these before Python packages because PyAudio needs PortAudio headers.
DEBIAN_PACKAGES=(
  build-essential cmake espeak-ng ffmpeg libasound2-dev libboost-all-dev
  liblapack-dev libopenblas-dev libsndfile1 portaudio19-dev python3.11-dev
  playerctl wmctrl xdotool brightnessctl
)
if command -v apt-get &>/dev/null; then
  echo "Installing required system packages: ${DEBIAN_PACKAGES[*]}"
  if [ "$EUID" -ne 0 ]; then SUDO='sudo'; else SUDO=''; fi
  $SUDO apt-get update
  $SUDO apt-get install -y "${DEBIAN_PACKAGES[@]}"
else
  echo "apt-get was not found; skipping Debian system packages."
  echo "Install these packages manually if your distribution uses another package manager:"
  echo "${DEBIAN_PACKAGES[*]}"
fi

# --- CREATE VIRTUAL ENVIRONMENT ---
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Creating virtual environment ($VENV_DIR)..."
  python$PYTHON_VERSION -m venv "$VENV_DIR"
else
  echo "Reusing existing virtual environment ($VENV_DIR)."
fi

# --- ACTIVATE VIRTUAL ENVIRONMENT ---
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# --- UPGRADE PIP ---
echo "Upgrading packaging tools..."
python -m pip install --upgrade pip 'setuptools<81' wheel

# --- INSTALL DEPENDENCIES ---
if [ -f "$REQUIREMENTS_FILE" ]; then
  echo "Installing dependencies from $REQUIREMENTS_FILE..."
  python -m pip install -r "$REQUIREMENTS_FILE"
else
  echo "No $REQUIREMENTS_FILE found."
  exit 1
fi

# --- LOCAL CONFIGURATION ---
if [ ! -f ".env" ] && [ -f ".env.template" ]; then
  cp ".env.template" ".env"
  echo "Created .env from .env.template. Add your provider credentials before running JARVIS."
fi

# --- FINISH ---
echo ""
echo "$PROJECT_NAME setup complete!"
echo "To activate your environment, run:"
echo "source $VENV_DIR/bin/activate"
echo ""
