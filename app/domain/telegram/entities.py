from dataclasses import dataclass
from typing import Optional, Literal

StateType = Literal["IDLE", "WAITING_INPUT"]

@dataclass
class TelegramUser:
    id: int
    first_name: str
    username: Optional[str]
    current_state: StateType = "IDLE"
    temp_data: Optional[dict] = None
    is_active: bool = True

    def activate(self):
        self.is_active = True

    def deactivate(self):
        self.is_active = False

    def change_state(self, new_state: StateType, temp_data: Optional[dict] = None):
        self.current_state = new_state
        self.temp_data = temp_data or {}
