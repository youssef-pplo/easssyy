# schemas.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

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
    token_type: str = "bearer"

class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class StudentProfileResponse(BaseModel):
    student_code: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    parent_phone: Optional[str] = None
    city: Optional[str] = None
    grade: Optional[str] = None
    password: str = "****"

class StudentEditRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    city: Optional[str] = None
    lang: Optional[str] = None
    grade: Optional[str] = None
    password: Optional[str] = None

class ReceiptCreate(BaseModel):
    student_code: str
    receipt_type: str
    item_id: str
    amount: float
    description: str

class ReceiptResponse(BaseModel):
    id: str = Field(alias="_id")
    student_id: str
    student_code: str
    receipt_type: str
    item_id: str
    amount: float
    description: str
    created_at: datetime

    class Config:
        arbitrary_types_allowed = True
        json_encoders = { ObjectId: str }
        allow_population_by_field_name = True

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# --- NEW SCHEMAS FOR EDUCATIONAL CONTENT ---

# 1. Schema for Chapters on the Homepage
class ChapterSummaryResponse(BaseModel):
    id: int
    image: str
    title: str
    price: str
    variant: str

# 2. Schema for Lessons inside a Chapter
class LessonSummaryResponse(BaseModel):
    id: int
    image: str
    title: str
    price: str
    isFree: bool

# 3. Schema for the detailed content of a Lesson
class LessonDetailResponse(BaseModel):
    id: int
    image: str
    title: str
    subject: str
    price: str
    duration: str
    exams: str
    questions: str
    isFree: bool

# 4. Schema for Books
class BookResponse(BaseModel):
    id: int
    title: str
    price: str
    image: str


class ItemPurchaseRequest(BaseModel):
    item_id: str
    item_type: str = Field(..., description="Type of item being purchased, e.g., 'chapter'")

class TestResultResponse(BaseModel):
    id: int
    test_name: str
    score: str
    date_taken: str
    review_link: str
    download_link: str

class AddTestResultRequest(BaseModel):
    test_name: str
    score: str

class VideoResponse(BaseModel):
    id: int
    title: str
    thumbnail_url: str
    video_url: str

class FavoriteVideoRequest(BaseModel):
    video_id: int

class ParentLoginRequest(BaseModel):
    student_phone: str
    parent_phone: str

class ParentDashboardResponse(BaseModel):
    student_info: StudentProfileResponse
    purchased_chapters: List[ChapterSummaryResponse]
    test_results: List[TestResultResponse]



class LoginResponseWithData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # Ensure this is always "bearer"
    data: StudentProfileResponse
