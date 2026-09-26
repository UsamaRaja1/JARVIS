import os
import re
import shutil
import subprocess
import time
import tkinter as tk
from difflib import get_close_matches
from tkinter import ttk

from src.configs import OS_TYPE
from src.utilz.logger import logger_
from src.utilz.switch_app import switch_application

PROJECT_DIRECTORIES = []

if OS_TYPE == "linux" and os.getenv("USER"):
    PROJECT_DIRECTORIES = [f"/home/{os.environ['USER']}/PycharmProjects", f"/home/{os.environ['USER']}/Projects"]

pycharm = shutil.which("pycharm") or shutil.which("pycharm-community")

if pycharm:
    print("Found:", pycharm)
    PYCHARM_EXECUTABLE = pycharm
else:
    print("PyCharm not found.")
    PYCHARM_EXECUTABLE = ""

PROJECT_COMMAND_PATTERNS = [
    r"(?:open|launch|start)\s+(?:the|my|a)?\s*([\w\s\-]+?)\s+project",  # open my xyz project
    r"(?:open|launch|start)\s+project\s+called\s+([\w\s\-]+)",  # open project called xyz
    r"(?:open|launch|start)\s+([\w\s\-]+)$",  # open xyz
    r"(?:open|launch|start)\s+([\w\s\-]+)\s+project",  # open xyz project
]


def extract_project_name(command: str) -> str | None:
    command = command.lower().strip()
    for pattern in PROJECT_COMMAND_PATTERNS:
        match = re.search(pattern, command)
        if match:
            return match.group(1).strip()
    return None


def find_pycharm_projects(base_dirs):
    projects = {}
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
        for root, dirs, _files in os.walk(base_dir):
            if ".idea" in dirs or ".git" in dirs:
                name = os.path.basename(root)
                projects[name.lower()] = root
    return projects


def match_project(user_query, projects):
    query = user_query.lower()
    project_names = list(projects.keys())
    matches = get_close_matches(query, project_names, n=10, cutoff=0.4)
    return matches


def open_pycharm_project(path):
    try:
        subprocess.Popen([PYCHARM_EXECUTABLE, path])
        logger_.info(f"Opening project: {path}")
        time.sleep(1.5)
        switch_application(f"open {path} Project")
    except Exception as e:
        logger_.error(f"Failed to open PyCharm project: {e}")


def show_all_projects():
    projects = find_pycharm_projects(PROJECT_DIRECTORIES)
    if not projects:
        logger_.info("No PyCharm projects found.")
        return

    matches = sorted(projects.keys())
    show_project_selection_window(matches, projects)


def show_project_selection_window(matches, projects, timeout=10):
    def on_double_click(event):
        selected = listbox.get(listbox.curselection())
        window.destroy()
        open_pycharm_project(projects[selected.lower()])

    def tick():
        nonlocal remaining_seconds, countdown_job
        if is_mouse_hovering:
            # Do not decrement while paused
            countdown_job = window.after(1000, tick)
            return

        if remaining_seconds <= 0:
            on_timeout()
        else:
            remaining_seconds -= 1
            countdown_label.config(text=f"Auto closing in {remaining_seconds} second{'s' if remaining_seconds != 1 else ''}...")
            countdown_job = window.after(1000, tick)

    def reset_countdown(event=None):
        nonlocal remaining_seconds, countdown_job
        remaining_seconds = timeout
        countdown_label.config(text=f"Auto closing in {remaining_seconds} seconds...")

        if countdown_job:
            window.after_cancel(countdown_job)

        if not is_mouse_hovering:
            countdown_job = window.after(1000, tick)

    def on_mouse_enter(event):
        nonlocal is_mouse_hovering, countdown_job
        is_mouse_hovering = True
        if countdown_job:
            window.after_cancel(countdown_job)
            countdown_job = None
        countdown_label.config(text="Timer paused while hovering")

    def on_mouse_leave(event):
        nonlocal is_mouse_hovering
        is_mouse_hovering = False
        countdown_label.config(text=f"Auto closing in {remaining_seconds} seconds...")
        # Resume countdown only if not already running
        if countdown_job is None:
            tick()

    def on_timeout():
        if window.winfo_exists():
            window.destroy()
            logger_.info("Popup auto-closed due to inactivity.")

    # Tk window setup
    window = tk.Tk()
    window.title("Select a PyCharm Project")
    window.geometry("420x340")
    window.configure(bg="#1e1e1e")

    style = ttk.Style(window)
    style.theme_use("default")
    custom_font = ("Calibri", 13)

    style.configure("TLabel", foreground="white", background="#1e1e1e", font=custom_font)
    style.map("TButton", foreground=[("active", "white")], background=[("active", "#444"), ("!active", "#2c2c2c")])

    label = ttk.Label(window, text="Select a project to open:", font=custom_font)
    label.pack(pady=(20, 10))

    frame = tk.Frame(window, bg="#1e1e1e")
    frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    listbox = tk.Listbox(
        frame, yscrollcommand=scrollbar.set, font=custom_font, selectbackground="#555", selectforeground="white", bg="#2c2c2c", fg="white", relief=tk.FLAT, highlightthickness=0, activestyle="none"
    )

    for project in matches:
        listbox.insert(tk.END, project)

    listbox.pack(fill=tk.BOTH, expand=True)
    listbox.bind("<Double-Button-1>", on_double_click)
    listbox.focus_set()
    scrollbar.config(command=listbox.yview)

    # Countdown label
    countdown_label = ttk.Label(window, text="", font=("Calibri", 11))
    countdown_label.pack(pady=(0, 10))

    # Bindings
    window.bind_all("<Button>", reset_countdown)
    window.bind("<Enter>", on_mouse_enter)
    window.bind("<Leave>", on_mouse_leave)

    # State variables
    countdown_job = None
    remaining_seconds = timeout
    is_mouse_hovering = False

    reset_countdown()

    window.mainloop()


def open_project_by_name(user_input, assistant=None):
    projects = find_pycharm_projects(PROJECT_DIRECTORIES)
    if not projects:
        assistant.say("No PyCharm projects found.")
        return

    user_input = extract_project_name(user_input)
    if user_input is None:
        return

    matches = match_project(user_input, projects)
    if not matches:
        assistant.say(f"No project found matching '{user_input}'.")
        return

    if len(matches) == 1:
        open_pycharm_project(projects[matches[0]])
    else:
        assistant.say(f"Multiple projects found matching '{user_input}'.")
        show_project_selection_window(matches, projects)


# Example usage
if __name__ == "__main__":
    query = input("What project do you want to open? ")
    open_project_by_name(query)
