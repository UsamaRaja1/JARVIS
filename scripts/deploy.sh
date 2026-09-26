#!/bin/bash

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
project_dir="$(dirname "$script_dir")"

APP_NAME="${APP_NAME:-jarvis}"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-src/jarvis_v2.py}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-jarvis}"

if ! command -v pm2 >/dev/null 2>&1; then
    echo "pm2 is not installed or not available in PATH."
    exit 1
fi

if ! command -v conda >/dev/null 2>&1; then
    echo "conda is not installed or not available in PATH."
    exit 1
fi

pm2_exists() {
    pm2 describe "$APP_NAME" >/dev/null 2>&1
}

save_pm2_state() {
    pm2 save
}

start() {
    if pm2_exists; then
        echo "PM2 app '$APP_NAME' is already registered. Restarting it."
        pm2 restart "$APP_NAME" --update-env
        save_pm2_state
        return
    fi

    echo "Starting '$APP_NAME' with pm2..."
    pm2 start bash \
        --name "$APP_NAME" \
        --cwd "$project_dir" \
        --time \
        -- -lc "source \"\$(conda info --base)/etc/profile.d/conda.sh\" && conda activate \"$CONDA_ENV_NAME\" && export PYTHONPATH=\"$project_dir\" PYTHONUNBUFFERED=1 && exec python -u \"$PYTHON_SCRIPT\""
    save_pm2_state
}

stop() {
    if pm2_exists; then
        echo "Stopping '$APP_NAME'..."
        pm2 stop "$APP_NAME"
    else
        echo "PM2 app '$APP_NAME' is not running."
    fi
}

restart() {
    if pm2_exists; then
        echo "Restarting '$APP_NAME'..."
        pm2 restart "$APP_NAME" --update-env
        save_pm2_state
    else
        start
    fi
}

status() {
    if pm2_exists; then
        pm2 status "$APP_NAME"
    else
        echo "PM2 app '$APP_NAME' is not registered."
        exit 1
    fi
}

logs() {
    pm2 logs "$APP_NAME"
}

delete_app() {
    if pm2_exists; then
        echo "Deleting '$APP_NAME' from pm2..."
        pm2 delete "$APP_NAME"
        save_pm2_state
    else
        echo "PM2 app '$APP_NAME' is not registered."
    fi
}

save() {
    echo "Saving pm2 process list..."
    pm2 save
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    restart) restart ;;
    status) status ;;
    logs) logs ;;
    delete) delete_app ;;
    save) save ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|delete|save}"
        exit 1
        ;;
esac
