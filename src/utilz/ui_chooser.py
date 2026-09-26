import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import filedialog, ttk
from typing import Any

from src.utilz.logger import logger_


@dataclass
class ChooserItem:
    label: str
    value: Any


def pick_file(title: str, initial_dir: str, extensions: list[str]) -> str | None:
    """Show the native OS file-open dialog, restricted to the given extensions. Returns the selected
    path, or None if the dialog could not be shown or the user cancelled."""
    filetypes = [("Supported media", " ".join(f"*.{ext}" for ext in extensions)), ("All files", "*.*")]
    try:
        window = tk.Tk()
        window.withdraw()
    except Exception as exc:
        logger_.warning(f"Failed to show file picker UI: {exc}")
        return None

    try:
        selected = filedialog.askopenfilename(title=title, initialdir=initial_dir, filetypes=filetypes, parent=window)
    finally:
        window.destroy()

    return selected or None


def show_chooser(title: str, prompt: str, items: list[ChooserItem], on_select: Callable[[Any], None], timeout: int = 10) -> bool:
    def choose_selected():
        selection = listbox.curselection()
        if not selection:
            return
        selected_item = items[selection[0]]
        window.destroy()
        on_select(selected_item.value)

    def on_double_click(_event):
        choose_selected()

    def tick():
        nonlocal remaining_seconds, countdown_job
        if is_mouse_hovering:
            countdown_job = window.after(1000, tick)
            return
        if remaining_seconds <= 0:
            on_timeout()
        else:
            remaining_seconds -= 1
            countdown_label.config(text=f"Auto closing in {remaining_seconds} second{'s' if remaining_seconds != 1 else ''}...")
            countdown_job = window.after(1000, tick)

    def reset_countdown(_event=None):
        nonlocal remaining_seconds, countdown_job
        remaining_seconds = timeout
        countdown_label.config(text=f"Auto closing in {remaining_seconds} seconds...")
        if countdown_job:
            window.after_cancel(countdown_job)
        if not is_mouse_hovering:
            countdown_job = window.after(1000, tick)

    def on_mouse_enter(_event):
        nonlocal is_mouse_hovering, countdown_job
        is_mouse_hovering = True
        if countdown_job:
            window.after_cancel(countdown_job)
            countdown_job = None
        countdown_label.config(text="Timer paused while hovering")

    def on_mouse_leave(_event):
        nonlocal is_mouse_hovering
        is_mouse_hovering = False
        countdown_label.config(text=f"Auto closing in {remaining_seconds} seconds...")
        if countdown_job is None:
            tick()

    def on_timeout():
        if window.winfo_exists():
            window.destroy()

    try:
        window = tk.Tk()
    except Exception as exc:
        logger_.warning(f"Failed to show chooser UI: {exc}")
        return False

    window.title(title)
    window.geometry("460x360")
    window.configure(bg="#1e1e1e")

    style = ttk.Style(window)
    style.theme_use("default")
    custom_font = ("Calibri", 13)
    style.configure("TLabel", foreground="white", background="#1e1e1e", font=custom_font)

    label = ttk.Label(window, text=prompt, font=custom_font)
    label.pack(pady=(20, 10))

    frame = tk.Frame(window, bg="#1e1e1e")
    frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    listbox = tk.Listbox(
        frame,
        yscrollcommand=scrollbar.set,
        font=custom_font,
        selectbackground="#555",
        selectforeground="white",
        bg="#2c2c2c",
        fg="white",
        relief=tk.FLAT,
        highlightthickness=0,
        activestyle="none",
    )

    for item in items:
        listbox.insert(tk.END, item.label)

    listbox.pack(fill=tk.BOTH, expand=True)
    listbox.bind("<Double-Button-1>", on_double_click)
    listbox.focus_set()
    scrollbar.config(command=listbox.yview)

    open_button = ttk.Button(window, text="Open", command=choose_selected)
    open_button.pack(pady=(0, 10))

    countdown_label = ttk.Label(window, text="", font=("Calibri", 11))
    countdown_label.pack(pady=(0, 10))

    window.bind_all("<Button>", reset_countdown)
    window.bind("<Enter>", on_mouse_enter)
    window.bind("<Leave>", on_mouse_leave)

    countdown_job = None
    remaining_seconds = timeout
    is_mouse_hovering = False

    reset_countdown()
    window.mainloop()
    return True
