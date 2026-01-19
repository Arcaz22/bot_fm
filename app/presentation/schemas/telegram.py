from pydantic import BaseModel
from typing import Optional

class Chat(BaseModel):
    id: int
    first_name: Optional[str] = None

class Message(BaseModel):
    message_id: int
    chat: Chat
    text: Optional[str] = None

class CallbackQuery(BaseModel):
    id: str
    data: Optional[str] = None
    message: Optional[Message] = None

class Update(BaseModel):
    update_id: int
    message: Optional[Message] = None
    edited_message: Optional[Message] = None
    callback_query: Optional[CallbackQuery] = None

class WebhookResponse(BaseModel):
    status: str
    message: str
