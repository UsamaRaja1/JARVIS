import json
import os

from src.configs import USER_CONFIG_FILE_PATH


class UserManager:
    def __init__(self, db_path=USER_CONFIG_FILE_PATH):
        self.db_path = db_path
        self.users = self.load_users()

    def load_users(self):
        if os.path.exists(self.db_path):
            with open(self.db_path) as f:
                return json.load(f)
        return {}

    def save_users(self):
        with open(self.db_path, "w") as f:
            json.dump(self.users, f, indent=4)

    def get_user(self, user_id):
        return self.users.get(user_id)

    def add_user(self, user_id, user_data):
        self.users[user_id] = user_data
        self.save_users()

    def update_user_workspace(self, user_id, new_workspace):
        user = self.get_user(user_id)
        if user:
            user["workspace"].update(new_workspace)
            self.save_users()

    def list_users(self):
        return list(self.users.keys())

    def delete_user(self, user_id):
        if user_id in self.users:
            del self.users[user_id]
            self.save_users()
