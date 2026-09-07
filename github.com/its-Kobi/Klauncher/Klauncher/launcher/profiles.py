import json
import re
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

@dataclass
class Profile:
    username: str
    uuid: str
    account_type: str = "offline"

class ProfileManager:
    """Manages offline profiles stored in a JSON file."""

    def __init__(self, profiles_file: Path):
        self.profiles_file = profiles_file
        self.profiles: List[Profile] = []
        self.load()

    def load(self) -> None:
        if self.profiles_file.exists():
            try:
                with open(self.profiles_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profiles = [Profile(**p) for p in data]
            except Exception:
                self.profiles = []

    def save(self) -> None:
        self.profiles_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.profiles_file, "w", encoding="utf-8") as f:
            json.dump([asdict(p) for p in self.profiles], f, indent=4)

    def create_profile(self, username: str) -> Profile:
        if not self.is_valid_username(username):
            raise ValueError("Invalid username. Must be 3-16 characters, letters, numbers, underscores.")
        if any(p.username.lower() == username.lower() for p in self.profiles):
            raise ValueError("Username already exists.")
        new_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"offline:{username.lower()}"))
        profile = Profile(username=username, uuid=new_uuid, account_type="offline")
        self.profiles.append(profile)
        self.save()
        return profile

    def delete_profile(self, profile_uuid: str) -> None:
        self.profiles = [p for p in self.profiles if p.uuid != profile_uuid]
        self.save()

    def get_profile(self, profile_uuid: str) -> Optional[Profile]:
        for p in self.profiles:
            if p.uuid == profile_uuid:
                return p
        return None

    def list_profiles(self) -> List[Profile]:
        return self.profiles.copy()

    @staticmethod
    def is_valid_username(username: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_]{3,16}", username))