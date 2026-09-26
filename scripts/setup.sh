#!/bin/bash
# ==========================================
# Jarvis Project Setup Script
# Python 3.11 + Virtual Environment (Linux)
# ==========================================

# Stop script on first error
set -e

# --- CONFIGURATION ---
PYTHON_VERSION=3.11
VENV_DIR=".venv"
REQUIREMENTS_FILE="requirements.txt"
PROJECT_NAME="Jarvis"

echo "🚀 Setting up $PROJECT_NAME environment..."

# --- CHECK PYTHON VERSION ---
if ! command -v python$PYTHON_VERSION &>/dev/null; then
  echo "❌ Python $PYTHON_VERSION is not installed. Please install it first."
  exit 1
fi

# --- CREATE VIRTUAL ENVIRONMENT ---
echo "📦 Creating virtual environment ($VENV_DIR)..."
python$PYTHON_VERSION -m venv $VENV_DIR

# --- ACTIVATE VIRTUAL ENVIRONMENT ---
echo "🔑 Activating virtual environment..."
source $VENV_DIR/bin/activate

# --- UPGRADE PIP ---
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# --- INSTALL DEPENDENCIES ---
if [ -f "$REQUIREMENTS_FILE" ]; then
  echo "📜 Installing dependencies from $REQUIREMENTS_FILE..."
  pip install -r $REQUIREMENTS_FILE
else
  echo "⚠️  No $REQUIREMENTS_FILE found. Skipping dependency installation."
fi

# --- OPTIONAL SYSTEM TOOLS (Debian/Ubuntu) ---
# These tools are useful for Jarvis features (media control, window management, TTS, brightness control).
DEBIAN_PACKAGES=(playerctl wmctrl espeak-ng xdotool brightnessctl)
if command -v apt-get &>/dev/null; then
  echo "🛠️  Installing required system packages: ${DEBIAN_PACKAGES[*]}"
  # Use sudo if not running as root
  if [ "$EUID" -ne 0 ]; then SUDO='sudo'; else SUDO=''; fi
  # Update package index and install packages non-interactively
  $SUDO apt-get update
  $SUDO apt-get install -y "${DEBIAN_PACKAGES[@]}"
else
  echo "⚠️  apt-get not found; skipping system package installation."
  echo "Please install the following packages manually if you need the related features: ${DEBIAN_PACKAGES[*]}"
fi

# --- FINISH ---
echo ""
echo "✅ $PROJECT_NAME setup complete!"
echo "To activate your environment, run:"
echo "source $VENV_DIR/bin/activate"
echo ""
