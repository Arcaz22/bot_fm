from pydantic import BaseModel
from typing import Optional, List

class Chat(BaseModel):
    id: int
    first_name: Optional[str] = None

class PhotoSize(BaseModel):
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: Optional[int] = None

class Message(BaseModel):
    message_id: int
    chat: Chat
    text: Optional[str] = None
    caption: Optional[str] = None
    photo: Optional[List[PhotoSize]] = None

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
