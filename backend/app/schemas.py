"""Request bodies (Pydantic)."""
from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=72)


class FilePatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    is_saved: bool | None = None


class ToolRun(BaseModel):
    file_ids: list[str] = Field(default_factory=list, max_length=200)
    params: dict = Field(default_factory=dict)


class WorkflowStep(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=20)


class WorkflowRun(BaseModel):
    file_ids: list[str] = Field(min_length=1, max_length=200)


class ReviewLinkIn(BaseModel):
    file_id: str
    title: str = Field(default="", max_length=255)


class CommentIn(BaseModel):
    author: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)
    page: int = Field(default=0, ge=0)
    x: float | None = None
    y: float | None = None
    parent_id: int | None = None


class SignerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    order: int = Field(default=1, ge=1, le=50)


class SignRequestIn(BaseModel):
    file_id: str
    title: str = Field(min_length=1, max_length=255)
    message: str = Field(default="", max_length=4000)
    signers: list[SignerIn] = Field(min_length=1, max_length=50)


class SignSubmit(BaseModel):
    image_data: str = Field(min_length=20, max_length=5_000_000)
    placements: list[dict] = Field(min_length=1, max_length=50)


class DeclineIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


class DscPrepareIn(BaseModel):
    file_id: str
    certificate: str = Field(min_length=20, max_length=200_000)
    page: int = 0
    rect: list[float] | None = None
    reason: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    contact: str = Field(default="", max_length=200)


class DscCompleteIn(BaseModel):
    state_token: str
    signature: str = Field(min_length=20, max_length=100_000)


class AiFileIn(BaseModel):
    file_id: str


class AiChatIn(BaseModel):
    file_id: str
    messages: list[dict] = Field(min_length=1, max_length=40)
