from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: str = "operator"


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)


class PasswordResetRequest(BaseModel):
    username: str = Field(..., min_length=1)
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)
    new_password: str = Field(..., min_length=6)


class ReportCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    priority: str = Field(default="Medium", min_length=1)


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class AdminUserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: str = "operator"


class AdminUserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None


class WebRTCOfferRequest(BaseModel):
    sdp: str
    type: str = "offer"
