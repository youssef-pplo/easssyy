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


# NEW: Schema that matches the requested format
class LessonResponseV2(BaseModel):
    id: str
    title: str
    description: Optional[str] = ""
    vimeo_embed_src: Optional[str] = ""
    image_url: Optional[str] = ""
    price: float
    hours: float  # Corrected from int to float to resolve validation error
    lecture: Optional[str] = ""
    course: Optional[str] = ""

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str

class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ContentUpdate(BaseModel):
    content: dict

class BookCreateRequest(BaseModel):
    title: str
    price: str
    image: str

class BookUpdateRequest(BaseModel):
    title: Optional[str] = None
    price: Optional[str] = None
    image: Optional[str] = None

# NEW: Admin registration and profile
class AdminRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    role: str = "admin"

class AdminProfileResponse(BaseModel):
    id: str = Field(alias="_id")
    email: EmailStr
    name: Optional[str] = None
    role: str

# NEW: Content management DTOs
class ChapterCreateRequest(BaseModel):
    title: str
    price: float = 0.0

class ChapterUpdateRequest(BaseModel):
    title: Optional[str] = None
    price: Optional[float] = None

class LessonCreateRequest(BaseModel):
    title: str
    chapter_id: int
    price: float = 0.0
    description: Optional[str] = ""
    vimeo_embed_src: Optional[str] = ""
    image_url: Optional[str] = ""
    hours: float = 0.0
    lecture: Optional[str] = ""
    isFree: bool = False

class LessonUpdateRequest(BaseModel):
    title: Optional[str] = None
    chapter_id: Optional[int] = None
    price: Optional[float] = None
    description: Optional[str] = None
    vimeo_embed_src: Optional[str] = None
    image_url: Optional[str] = None
    hours: Optional[float] = None
    lecture: Optional[str] = None
    isFree: Optional[bool] = None

# NEW: Payment DTOs (Paymob scaffolding)
class PaymentInitiateRequest(BaseModel):
    item_type: str
    item_id: str
    payment_method: Optional[str] = "card"

class PaymentInitiateResponse(BaseModel):
    merchant_order_id: str
    status: str
    redirect_url: Optional[str] = None

class PaymentStatusResponse(BaseModel):
    merchant_order_id: str
    status: str
    paymob_order_id: Optional[int] = None
    amount: float

# NEW: Teacher DTOs
class TeacherCreateRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None

class TeacherLoginRequest(BaseModel):
    email: EmailStr
    password: str

class TeacherProfileResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: EmailStr
    phone: Optional[str] = None

class TeacherUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None