import os
import re
import subprocess

from src.utilz.logger import logger_


def list_open_applications():
    result = subprocess.run(["wmctrl", "-lx"], stdout=subprocess.PIPE, text=True)
    applications = result.stdout.strip().split("\n")
    return applications


def switch_to_application(application_id):
    subprocess.run(["xdotool", "windowactivate", application_id])


APP_COMMANDS = {"system monitor": "gnome-system-monitor", "slack": "slack", "pycharm": "pycharm", "vlc": "vlc", "file manager": "nautilus", "new terminal": "gnome-terminal", "google": "google-chrome"}


def open_application(spoken_text):
    for key in APP_COMMANDS:
        if key in spoken_text.lower():
            try:
                os.system(APP_COMMANDS[key])
                logger_.info(f"Launching {key}")
                return f"Opening {key}."
            except Exception as e:
                logger_.error(f"Failed to open {key}: {e}")
                return f"Sorry, I couldn't open {key}."

    try:
        process = spoken_text.split("open")[1].split()[0]
        os.system(process)
        return f"Opening {process}."
    except Exception as e:
        logger_.error(f"Failed to open {process}: {e}")
        return f"Sorry, I couldn't open {process}."


def switch_application(query):
    try:
        matches = re.search(r"open (.\w+)", query)
        if matches:
            w = matches.group(1).lower()
            applications = list_open_applications()
            if applications:
                desktop_num = get_current_desktop_id()
                application_found = False
                # Check if it's opened in the current desktop
                for _i, win in enumerate(applications):
                    if w in win.lower() and desktop_num == int(win.split()[1]):
                        application_id = win.split()[0]
                        switch_to_application(application_id)
                        application_found = True
                        break

                # Check in all the desktops
                if not application_found:
                    for win in applications:
                        if w in win.lower():
                            application_id = win.split()[0]
                            switch_to_application(application_id)
                            application_found = True
                            break

                if not application_found:
                    response = open_application(query)
                    if response != "Application not found.":
                        return response
                    else:
                        return f"{w.title()} is not open."
                else:
                    return f"Opening {w.title()}"
        return ""

    except Exception as e:
        logger_.error(str(e))
        return ""


def get_current_desktop_id():
    result = subprocess.run(["wmctrl", "-d"], stdout=subprocess.PIPE, text=True)
    result = result.stdout.strip().split("\n")
    result = [int(r.split()[0]) for r in result if "*" in r]
    return result[0]


def switch_desktop(desktop_num):
    # Use wmctrl to switch to the desired workspace
    try:
        # Check if wmctrl is installed
        if os.system("command -v wmctrl > /dev/null") != 0:
            raise Exception("wmctrl is not installed. Please install it using 'sudo apt install wmctrl'.")

        # Switch to the specified workspace (workspace indexing starts at 0)
        os.system(f"wmctrl -s {desktop_num - 1}")

    except Exception as e:
        logger_.error(f"Failed to switch to desktop {desktop_num}: {e}")
        return f"Failed to switch to desktop {desktop_num}: {e}"
