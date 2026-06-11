import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class Credentials(BaseModel):
    product_id: uuid.UUID
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Password must not exceed 72 bytes")
        return value


class UserResponse(BaseModel):
    user_id: uuid.UUID


class MigratedUser(BaseModel):
    product_id: uuid.UUID
    email: EmailStr
    password_hash: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class MessageResponse(BaseModel):
    detail: str
