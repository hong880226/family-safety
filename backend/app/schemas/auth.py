"""Auth schemas."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    family_id: int | None = None
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=4)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    member_id: int
    role: str


class TokenPayload(BaseModel):
    sub: str  # member id
    family_id: int
    role: str
    exp: int
