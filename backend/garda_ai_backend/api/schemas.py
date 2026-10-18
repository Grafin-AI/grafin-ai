from pydantic import BaseModel


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: login is an exact lookup, and EmailStr rejects
    # reserved domains (e.g. the seeded admin@garda.local) with a 422.
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: str
    role: str
