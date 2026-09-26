import json
from multiprocessing import Queue

from src.configs import SHARED_DATA_FILE_PATH

# def get_name():
#     return global_state["name"]
#
#
# def set_name(name):
#     global_state["name"] = name
#
# def get_name():
#     return os.environ.get("SHARED_NAMES")
#
#
# def set_name(name):
#     os.environ["SHARED_NAMES"] = name


def get_name():
    try:
        with open(SHARED_DATA_FILE_PATH) as f:
            data = json.load(f)
        return data.get("names", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading data from shared_data.json: {e}")
        return []


def set_name(name):
    with open(SHARED_DATA_FILE_PATH, "w") as f:
        json.dump({"names": name}, f)


class GlobalState:
    def __init__(self):
        self.name = "None"

    def get_name(self):
        return self.name

    def set_name(self, name):
        self.name = name


if __name__ == "__main__":
    gs = GlobalState()
    prev_name = ""

    # shared_string = Value(ctypes.c_char_p, b'')
    queue = Queue()
    print(f"Name get: {get_name()}")

    # Use a dictionary to hold the name
    global_state = {"name": "None"}

    # while True:
    #     name = get_name()
    #     if name != prev_name:
    #         print(f"name: {name}")
    #         prev_name = name
    #     # time.sleep(.1)
