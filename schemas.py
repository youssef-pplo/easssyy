# schemas.py
from pydantic import BaseModel, Field
from typing import Optional

class RegisterRequest(BaseModel):
    name: str
    phone: str
    email: str
    parent_phone: str
    city: str
    grade: str
    lang: str
    password: str
    confirm_password: str

class LoginRequest(BaseModel):
    identifier: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str

class StudentProfileResponse(BaseModel):
    student_code: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    parent_phone: Optional[str] = None
    city: Optional[str] = None
    lang: Optional[str] = None
    grade: Optional[str] = None
    password: str = "****" # Always masked

class StudentEditRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    city: Optional[str] = None
    lang: Optional[str] = None
    grade: Optional[str] = None
    password: Optional[str] = None
