import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr | None = None
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    title: str = "New Chat"
    model_name: str | None = None


class SessionResponse(BaseModel):
    id: uuid.UUID
    title: str
    model_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    model_name: str | None = None
    message: str = Field(min_length=1)
    use_swarm: bool = False
    attachments: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str
    session_id: uuid.UUID
    model_name: str
    tool_calls_made: list[str] = []
    agents_used: list[str] = []


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str = ""
    tier: str = "free"
    backend: str = "mlx"
    available: bool = True
    supports_tools: bool = False
    description: str = ""
    context_k: int = 8


class ScheduleSkillRequest(BaseModel):
    skill_name: str
    interval_minutes: int = Field(ge=1, le=1440)
    args: dict = Field(default_factory=dict)


class ScheduleSkillResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    message: str


class SkillInfo(BaseModel):
    name: str
    description: str


class SkillExecuteRequest(BaseModel):
    skill_name: str
    args: dict = Field(default_factory=dict)


class SkillExecuteResponse(BaseModel):
    task_id: str
    status: str


class SkillTaskStatus(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class AsyncChatResponse(BaseModel):
    task_id: str
    status: str


class AsyncTaskStatus(BaseModel):
    task_id: str
    status: str
    result: dict | None = None
    error: str | None = None


class TestResult(BaseModel):
    name: str
    module: str
    status: str
    message: str
    details: dict = Field(default_factory=dict)
    tested_at: str


class TestSuiteResponse(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[TestResult]
    ports: dict = Field(default_factory=dict)
