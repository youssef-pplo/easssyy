# main.py
from fastapi import FastAPI, HTTPException, Depends, status, Response, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse, FileResponse
from passlib.hash import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import random
import string
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from database import (
    connect_to_mongo, close_mongo_connection, get_student_collection,
    get_token_blacklist_collection, get_receipt_collection,
    get_password_reset_collection,
    get_favorite_videos_collection,
    get_educational_content_collection,
    get_books_collection,
    get_mock_test_results_collection,
    get_mock_videos_collection,
    get_admins_collection,
    get_teachers_collection,
    get_payments_collection,
    get_paymob_logs_collection
)
from schemas import (
    RegisterRequest, LoginRequest, TokenResponse, RefreshTokenResponse,
    StudentEditRequest, StudentProfileResponse,
    ReceiptCreate, ReceiptResponse,
    ForgotPasswordRequest, VerifyResetCodeRequest, ResetPasswordRequest,
    ChapterSummaryResponse, LessonSummaryResponse, LessonDetailResponse,
    BookResponse, ItemPurchaseRequest, TestResultResponse,
    AddTestResultRequest, VideoResponse, FavoriteVideoRequest,
    ParentLoginRequest, ParentDashboardResponse, LoginResponseWithData,
    LessonResponseV2,
    # New Admin Schemas
    AdminLoginRequest, AdminTokenResponse, ContentUpdate,
    BookCreateRequest, BookUpdateRequest,
    AdminRegisterRequest, AdminProfileResponse,
    ChapterCreateRequest, ChapterUpdateRequest,
    LessonCreateRequest, LessonUpdateRequest,
    PaymentInitiateRequest, PaymentInitiateResponse, PaymentStatusResponse,
    TeacherCreateRequest, TeacherLoginRequest, TeacherProfileResponse, TeacherUpdateRequest
)
from motor.motor_asyncio import AsyncIOMotorCollection

GRADE_MAP = {
    "10": "الصف الأول الثانوي",
    "11": "الصف الثاني الثانوي",
    "12": "الصف الثالث الثانوي",
}
GRADE_MAP_REVERSE = {v: k for k, v in GRADE_MAP.items()}

# --- Constants for image URLs ---
courseImg = "https://image-placeholder.com/images/actual-size/200x200.png"
bookImg = "https://image-placeholder.com/images/actual-size/150x200.png"

def format_student_grade(student: dict):
    if student and "grade" in student and student.get("grade") in GRADE_MAP:
        student["grade"] = GRADE_MAP[student["grade"]]
    return student

# NEW: A helper function to convert integer keys to strings
def convert_dict_keys_to_str(d):
    new_d = {}
    for k, v in d.items():
        if isinstance(v, dict):
            new_d[str(k)] = convert_dict_keys_to_str(v)
        else:
            new_d[str(k)] = v
    return new_d



@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    # Seed a default admin user if it does not exist
    try:
        admins_collection = await get_admins_collection()
        default_email = "admin@easybio.com"
        default_password = "Admin@123"
        existing = await admins_collection.find_one({"email": default_email})
        if not existing:
            await admins_collection.insert_one({
                "email": default_email,
                "password": hash_password(default_password),
                "name": "Super Admin",
                "role": "admin",
                "created_at": datetime.now(timezone.utc)
            })
            print(f"Seeded default admin: {default_email}")
    except Exception as e:
        print("Default admin seeding failed:", e)
    yield
    await close_mongo_connection()

app = FastAPI(lifespan=lifespan)

# --- Configuration & Middleware ---
SECRET_KEY = "Ea$yB1o"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
SMTP_HOST, SMTP_PORT = 'smtp.hostinger.com', 587
SMTP_USERNAME, SMTP_PASSWORD = 'noreply@easybio-drabdelrahman.com', 'Webacc@123'

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173", "http://localhost:8000", "https://easybio2025.netlify.app"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- Helper & Auth Functions ---
def create_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
def create_access_token(subject: str): return create_token({"sub": subject}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
def create_refresh_token(subject: str):
    expire_delta, expire_utc = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return create_token({"sub": subject}, expire_delta), expire_utc
def create_password_reset_token(email: str, scope: str, minutes: int): return create_token({"sub": email, "scope": scope}, timedelta(minutes=minutes))
def verify_password(plain, hashed): return bcrypt.verify(plain, hashed)
def hash_password(password): return bcrypt.hash(password)
def generate_student_code(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
def decode_token(token: str):
    try: return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError: return None

# --- Role-based token helpers ---
def create_admin_access_token(admin_id: str):
    return create_token({"sub": admin_id, "role": "admin"}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

def create_teacher_access_token(teacher_id: str):
    return create_token({"sub": teacher_id, "role": "teacher"}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
def send_password_reset_email(email: str, code: str):
    msg = MIMEText(f"Your password reset code is: {code}\nIt is valid for 10 minutes.")
    msg['Subject'], msg['From'], msg['To'] = 'Your Password Reset Code', SMTP_USERNAME, email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"Password reset code sent to {email}")
    except Exception as e: print(f"Failed to send email to {email}. Error: {e}")
async def get_current_student(token: str = Depends(oauth2_scheme), student_collection: AsyncIOMotorCollection = Depends(get_student_collection)):
    payload = decode_token(token)
    if not payload or not (sub := payload.get("sub")): raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    student = await student_collection.find_one({"_id": ObjectId(sub)})
    if not student: raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    return student

async def get_current_admin(token: str = Depends(oauth2_scheme), admins: AsyncIOMotorCollection = Depends(get_admins_collection)):
    payload = decode_token(token)
    if not payload or payload.get("role") != "admin" or not (sub := payload.get("sub")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin token")
    admin = await admins.find_one({"_id": ObjectId(sub)})
    if not admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Admin not found")
    return admin

async def get_current_teacher(token: str = Depends(oauth2_scheme), teachers: AsyncIOMotorCollection = Depends(get_teachers_collection)):
    payload = decode_token(token)
    if not payload or payload.get("role") != "teacher" or not (sub := payload.get("sub")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid teacher token")
    teacher = await teachers.find_one({"_id": ObjectId(sub)})
    if not teacher:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Teacher not found")
    return teacher

# Add a new helper function to find content details
async def find_item_in_content_by_id(item_id_to_find: int):
    """Finds a chapter or lesson by its ID in the database content."""
    edu_collection = await get_educational_content_collection()
    edu_doc = await edu_collection.find_one({})
    if not edu_doc:
        return None
    content = edu_doc.get("content", {})
    # Iterate through the converted string keys
    for year_content in content.values():
        for term_content in year_content.values():
            for lang_content in term_content.values():
                for subject_content in lang_content.values():
                    # Check for the item with the converted string key
                    if str(item_id_to_find) in subject_content.get("chapters", {}):
                        return subject_content["chapters"][str(item_id_to_find)]
    return None

# --- API Endpoints ---
@app.get("/")
def root(): return {"status": "ok"}

# ----------------------
# ADMIN AUTH ENDPOINTS
# ----------------------

@app.post("/admin/register", response_model=AdminProfileResponse)
async def admin_register(
    data: AdminRegisterRequest,
    admins: AsyncIOMotorCollection = Depends(get_admins_collection)
):
    existing = await admins.find_one({"email": data.email})
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin already exists")
    admin_doc = {
        "email": data.email,
        "password": hash_password(data.password),
        "name": data.name,
        "role": data.role,
        "created_at": datetime.now(timezone.utc)
    }
    result = await admins.insert_one(admin_doc)
    created = await admins.find_one({"_id": result.inserted_id})
    created["_id"] = str(created["_id"])
    created.pop("password", None)
    return created

@app.post("/admin/login", response_model=AdminTokenResponse)
async def admin_login(
    data: AdminLoginRequest,
    admins: AsyncIOMotorCollection = Depends(get_admins_collection)
):
    admin = await admins.find_one({"email": data.email})
    if not admin or not verify_password(data.password, admin.get("password", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_admin_access_token(str(admin["_id"]))
    return {"access_token": token, "token_type": "bearer"}

@app.get("/admin/profile", response_model=AdminProfileResponse)
async def admin_profile(current_admin: dict = Depends(get_current_admin)):
    current_admin = {**current_admin}
    current_admin["_id"] = str(current_admin["_id"])
    current_admin.pop("password", None)
    return current_admin


# ----------------------
# TEACHER AUTH ENDPOINTS
# ----------------------

@app.post("/teacher/register", response_model=TeacherProfileResponse)
async def teacher_register(
    data: TeacherCreateRequest,
    teachers: AsyncIOMotorCollection = Depends(get_teachers_collection)
):
    exists = await teachers.find_one({"email": data.email})
    if exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Teacher already exists")
    teacher_doc = {
        "name": data.name,
        "email": data.email,
        "phone": data.phone,
        "password": hash_password(data.password),
        "role": "teacher",
        "created_at": datetime.now(timezone.utc)
    }
    result = await teachers.insert_one(teacher_doc)
    created = await teachers.find_one({"_id": result.inserted_id})
    created["_id"] = str(created["_id"])
    created.pop("password", None)
    return created

@app.post("/teacher/login", response_model=TokenResponse)
async def teacher_login(
    data: TeacherLoginRequest,
    teachers: AsyncIOMotorCollection = Depends(get_teachers_collection)
):
    teacher = await teachers.find_one({"email": data.email})
    if not teacher or not verify_password(data.password, teacher.get("password", "")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_teacher_access_token(str(teacher["_id"]))
    return {"access_token": token, "token_type": "bearer"}

@app.get("/teacher/profile", response_model=TeacherProfileResponse)
async def teacher_profile(current_teacher: dict = Depends(get_current_teacher)):
    current_teacher = {**current_teacher}
    current_teacher["_id"] = str(current_teacher["_id"])
    current_teacher.pop("password", None)
    return current_teacher


# ----------------------
# ADMIN CONTENT MANAGEMENT
# ----------------------

async def _get_or_create_content_doc(edu_collection: AsyncIOMotorCollection) -> dict:
    doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not doc:
        result = await edu_collection.insert_one({"content": {}, "created_at": datetime.now(timezone.utc)})
        doc = await edu_collection.find_one({"_id": result.inserted_id})
    return doc

def _ensure_subject_path(content_root: dict, year: str, term: str, language: str, subject: str) -> None:
    content_root.setdefault(year, {})
    content_root[year].setdefault(term, {})
    content_root[year][term].setdefault(language, {})
    content_root[year][term][language].setdefault(subject, {"chapters": {}, "lessons": {}})

@app.get("/admin/content/{year}/{term}/{language}/{subject}")
async def admin_get_subject_content(
    year: str, term: str, language: str, subject: str,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return content[year][term][language][subject]

@app.post("/admin/content/{year}/{term}/{language}/{subject}/chapters")
async def admin_create_chapter(
    year: str, term: str, language: str, subject: str,
    body: ChapterCreateRequest,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    chapters = content[year][term][language][subject]["chapters"]
    new_id = 1
    if chapters:
        try:
            new_id = max(int(k) for k in chapters.keys()) + 1
        except Exception:
            new_id = 1
    chapters[str(new_id)] = {
        "title": body.title,
        "price": f"{body.price} جنية"
    }
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return {"id": new_id, **chapters[str(new_id)]}

@app.put("/admin/content/{year}/{term}/{language}/{subject}/chapters/{chapter_id}")
async def admin_update_chapter(
    year: str, term: str, language: str, subject: str, chapter_id: int,
    body: ChapterUpdateRequest,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    chapters = content[year][term][language][subject]["chapters"]
    key = str(chapter_id)
    if key not in chapters:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapter not found")
    if body.title is not None:
        chapters[key]["title"] = body.title
    if body.price is not None:
        chapters[key]["price"] = f"{body.price} جنية"
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return {"id": chapter_id, **chapters[key]}

@app.delete("/admin/content/{year}/{term}/{language}/{subject}/chapters/{chapter_id}")
async def admin_delete_chapter(
    year: str, term: str, language: str, subject: str, chapter_id: int,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    chapters = content[year][term][language][subject]["chapters"]
    key = str(chapter_id)
    if key not in chapters:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapter not found")
    # Remove all lessons that belong to this chapter as well
    lessons = content[year][term][language][subject]["lessons"]
    to_delete_lessons = [lid for lid, ldata in lessons.items() if ldata.get("chapter_id") == chapter_id]
    for lid in to_delete_lessons:
        lessons.pop(lid, None)
    deleted = chapters.pop(key)
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return {"message": "Chapter deleted", "deleted": {"id": chapter_id, **deleted}}

@app.post("/admin/content/{year}/{term}/{language}/{subject}/lessons")
async def admin_create_lesson(
    year: str, term: str, language: str, subject: str,
    body: LessonCreateRequest,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    subject_node = content[year][term][language][subject]
    if str(body.chapter_id) not in subject_node["chapters"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "chapter_id does not exist")
    lessons = subject_node["lessons"]
    new_id = 1
    if lessons:
        try:
            new_id = max(int(k) for k in lessons.keys()) + 1
        except Exception:
            new_id = 1
    lessons[str(new_id)] = {
        "title": body.title,
        "chapter_id": int(body.chapter_id),
        "price": f"{body.price} جنية",
        "description": body.description or "",
        "vimeo_embed_src": body.vimeo_embed_src or "",
        "image_url": body.image_url or "",
        "hours": float(body.hours or 0),
        "lecture": body.lecture or "",
        "isFree": bool(body.isFree)
    }
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return {"id": new_id, **lessons[str(new_id)]}

@app.put("/admin/content/{year}/{term}/{language}/{subject}/lessons/{lesson_id}")
async def admin_update_lesson(
    year: str, term: str, language: str, subject: str, lesson_id: int,
    body: LessonUpdateRequest,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    node = content[year][term][language][subject]
    lessons = node["lessons"]
    key = str(lesson_id)
    if key not in lessons:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    if body.title is not None:
        lessons[key]["title"] = body.title
    if body.chapter_id is not None:
        if str(body.chapter_id) not in node["chapters"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "chapter_id does not exist")
        lessons[key]["chapter_id"] = int(body.chapter_id)
    if body.price is not None:
        lessons[key]["price"] = f"{body.price} جنية"
    if body.description is not None:
        lessons[key]["description"] = body.description
    if body.vimeo_embed_src is not None:
        lessons[key]["vimeo_embed_src"] = body.vimeo_embed_src
    if body.image_url is not None:
        lessons[key]["image_url"] = body.image_url
    if body.hours is not None:
        lessons[key]["hours"] = float(body.hours)
    if body.lecture is not None:
        lessons[key]["lecture"] = body.lecture
    if body.isFree is not None:
        lessons[key]["isFree"] = bool(body.isFree)
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return {"id": lesson_id, **lessons[key]}

@app.delete("/admin/content/{year}/{term}/{language}/{subject}/lessons/{lesson_id}")
async def admin_delete_lesson(
    year: str, term: str, language: str, subject: str, lesson_id: int,
    _: dict = Depends(get_current_admin),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    doc = await _get_or_create_content_doc(edu_collection)
    content = doc.get("content", {})
    _ensure_subject_path(content, year, term, language, subject)
    lessons = content[year][term][language][subject]["lessons"]
    key = str(lesson_id)
    if key not in lessons:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")
    deleted = lessons.pop(key)
    await edu_collection.update_one({"_id": doc["_id"]}, {"$set": {"content": content}})
    return {"message": "Lesson deleted", "deleted": {"id": lesson_id, **deleted}}


# ----------------------
# BOOKS MANAGEMENT (ADMIN)
# ----------------------

@app.get("/admin/books", response_model=List[BookResponse])
async def admin_list_books(
    _: dict = Depends(get_current_admin),
    books_collection: AsyncIOMotorCollection = Depends(get_books_collection)
):
    return await books_collection.find().to_list(1000)

@app.post("/admin/books", response_model=BookResponse)
async def admin_create_book(
    body: BookCreateRequest,
    _: dict = Depends(get_current_admin),
    books_collection: AsyncIOMotorCollection = Depends(get_books_collection)
):
    existing = await books_collection.find({}, {"id": 1}).sort("id", -1).limit(1).to_list(1)
    new_id = (existing[0]["id"] + 1) if existing else 1
    doc = {"id": new_id, "title": body.title, "price": body.price, "image": body.image}
    await books_collection.insert_one(doc)
    return doc

@app.put("/admin/books/{book_id}", response_model=BookResponse)
async def admin_update_book(
    book_id: int,
    body: BookUpdateRequest,
    _: dict = Depends(get_current_admin),
    books_collection: AsyncIOMotorCollection = Depends(get_books_collection)
):
    update = {k: v for k, v in body.dict(exclude_unset=True).items()}
    await books_collection.update_one({"id": book_id}, {"$set": update})
    updated = await books_collection.find_one({"id": book_id})
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found")
    return updated

@app.delete("/admin/books/{book_id}")
async def admin_delete_book(
    book_id: int,
    _: dict = Depends(get_current_admin),
    books_collection: AsyncIOMotorCollection = Depends(get_books_collection)
):
    result = await books_collection.find_one_and_delete({"id": book_id})
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Book not found")
    return {"message": "Book deleted"}


# ----------------------
# PAYMENTS (PAYMOB SCAFFOLD)
# ----------------------

def _generate_merchant_order_id() -> str:
    return f"ORD-{int(datetime.now(timezone.utc).timestamp())}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

async def _resolve_item_amount(item_type: str, item_id: str, edu_collection: AsyncIOMotorCollection) -> float:
    if item_type == "chapter":
        try:
            item = await find_item_in_content_by_id(int(item_id))
        except Exception:
            item = None
        if item:
            price_str = str(item.get("price", "0 جنية")).split()[0]
            try:
                return float(price_str)
            except Exception:
                return 0.0
    return 0.0

@app.post("/payments/initiate", response_model=PaymentInitiateResponse)
async def initiate_payment(
    body: PaymentInitiateRequest,
    current_student: dict = Depends(get_current_student),
    payments: AsyncIOMotorCollection = Depends(get_payments_collection),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    amount = await _resolve_item_amount(body.item_type, body.item_id, edu_collection)
    merchant_order_id = _generate_merchant_order_id()
    payment_doc = {
        "merchant_order_id": merchant_order_id,
        "student_id": str(current_student["_id"]),
        "student_code": current_student.get("student_code"),
        "item_type": body.item_type,
        "item_id": body.item_id,
        "amount": float(amount),
        "status": "pending",
        "payment_method": body.payment_method,
        "created_at": datetime.now(timezone.utc)
    }
    await payments.insert_one(payment_doc)
    redirect_url = f"https://paymob.example/checkout/{merchant_order_id}"
    return {"merchant_order_id": merchant_order_id, "status": "pending", "redirect_url": redirect_url}

@app.post("/payments/webhook")
async def paymob_webhook(
    payload: dict,
    payments: AsyncIOMotorCollection = Depends(get_payments_collection),
    paymob_logs: AsyncIOMotorCollection = Depends(get_paymob_logs_collection),
    receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection),
    student_collection: AsyncIOMotorCollection = Depends(get_student_collection)
):
    try:
        await paymob_logs.insert_one({"payload": payload, "received_at": datetime.now(timezone.utc)})
    except Exception:
        pass

    merchant_order_id = payload.get("merchant_order_id") or payload.get("order"); paymob_order_id = payload.get("id") or payload.get("paymob_order_id")
    success = bool(payload.get("success") or payload.get("is_paid") or payload.get("successfully_paid"))
    if not merchant_order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "merchant_order_id missing")

    payment = await payments.find_one({"merchant_order_id": merchant_order_id})
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")

    new_status = "paid" if success else "failed"
    await payments.update_one({"_id": payment["_id"]}, {"$set": {"status": new_status, "paymob_order_id": paymob_order_id, "webhook_payload": payload}})

    if success:
        # Create a receipt record for the student
        student_id = payment.get("student_id")
        student = await student_collection.find_one({"_id": ObjectId(student_id)}) if student_id else None
        student_code = student.get("student_code") if student else None
        receipt = {
            "student_id": student_id,
            "student_code": student_code,
            "receipt_type": "package_purchase",
            "item_id": payment.get("item_id"),
            "amount": float(payment.get("amount", 0.0)),
            "description": f"Purchase of {payment.get('item_type')} {payment.get('item_id')} (Paymob)",
            "created_at": datetime.now(timezone.utc)
        }
        try:
            await receipt_collection.insert_one(receipt)
        except Exception:
            pass

    return {"message": "ok"}

@app.get("/payments/status/{merchant_order_id}", response_model=PaymentStatusResponse)
async def payment_status(
    merchant_order_id: str,
    current_student: dict = Depends(get_current_student),
    payments: AsyncIOMotorCollection = Depends(get_payments_collection)
):
    payment = await payments.find_one({"merchant_order_id": merchant_order_id, "student_id": str(current_student["_id"])})
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return {
        "merchant_order_id": payment["merchant_order_id"],
        "status": payment.get("status", "pending"),
        "paymob_order_id": payment.get("paymob_order_id"),
        "amount": float(payment.get("amount", 0.0))
    }

@app.get("/dashboard/my-payments")
async def my_payments(
    current_student: dict = Depends(get_current_student),
    payments: AsyncIOMotorCollection = Depends(get_payments_collection)
):
    cursor = payments.find({"student_id": str(current_student["_id"])})
    docs = await cursor.to_list(1000)
    for d in docs:
        d["_id"] = str(d["_id"]) if "_id" in d else None
    return docs

@app.get("/admin/payments")
async def admin_list_payments(
    _: dict = Depends(get_current_admin),
    payments: AsyncIOMotorCollection = Depends(get_payments_collection)
):
    return await payments.find().sort("created_at", -1).to_list(1000)


# ----------------------
# ADMIN DASHBOARD METRICS
# ----------------------

@app.get("/admin/dashboard")
async def admin_dashboard(
    _: dict = Depends(get_current_admin),
    student_collection: AsyncIOMotorCollection = Depends(get_student_collection),
    receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection),
    books_collection: AsyncIOMotorCollection = Depends(get_books_collection),
    payments: AsyncIOMotorCollection = Depends(get_payments_collection)
):
    total_students = await student_collection.count_documents({})
    total_receipts = await receipt_collection.count_documents({})
    receipts_cursor = receipt_collection.find({}, {"amount": 1})
    receipts = await receipts_cursor.to_list(10000)
    total_revenue = sum(float(r.get("amount", 0)) for r in receipts)
    total_books = await books_collection.count_documents({})
    recent_payments = await payments.find().sort("created_at", -1).limit(10).to_list(10)
    return {
        "total_students": total_students,
        "total_receipts": total_receipts,
        "total_revenue": total_revenue,
        "total_books": total_books,
        "recent_payments": recent_payments
    }

@app.get("/admin/students")
async def admin_list_students(
    _: dict = Depends(get_current_admin),
    student_collection: AsyncIOMotorCollection = Depends(get_student_collection)
):
    # Note: This returns hashed passwords, so we remove them
    students = await student_collection.find().to_list(1000)
    for s in students:
        s.pop("password", None)
        s["_id"] = str(s["_id"]) if "_id" in s else None
    return students

@app.get("/admin/receipts")
async def admin_list_receipts(
    _: dict = Depends(get_current_admin),
    receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection)
):
    receipts = await receipt_collection.find().sort("created_at", -1).to_list(1000)
    for r in receipts:
        r["_id"] = str(r["_id"]) if "_id" in r else None
    return receipts

@app.get("/admin/teachers")
async def admin_list_teachers(
    _: dict = Depends(get_current_admin),
    teachers: AsyncIOMotorCollection = Depends(get_teachers_collection)
):
    docs = await teachers.find().to_list(1000)
    for d in docs:
        d.pop("password", None)
        d["_id"] = str(d["_id"]) if "_id" in d else None
    return docs

@app.put("/teacher/profile", response_model=TeacherProfileResponse)
async def update_teacher_profile(
    body: TeacherUpdateRequest,
    current_teacher: dict = Depends(get_current_teacher),
    teachers: AsyncIOMotorCollection = Depends(get_teachers_collection)
):
    update = {k: v for k, v in body.dict(exclude_unset=True).items()}
    if "password" in update and update["password"]:
        update["password"] = hash_password(update["password"])
    elif "password" in update:
        update.pop("password", None)
    await teachers.update_one({"_id": current_teacher["_id"]}, {"$set": update})
    updated = await teachers.find_one({"_id": current_teacher["_id"]})
    updated["_id"] = str(updated["_id"])
    updated.pop("password", None)
    return updated

@app.post("/register")
async def register(data: RegisterRequest, students: AsyncIOMotorCollection = Depends(get_student_collection)):
    if await students.find_one({"$or": [{"phone": data.phone}, {"email": data.email}]}):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone or Email already exists")
    if data.password != data.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")

    s_data = data.dict()
    if s_data.get("grade") in GRADE_MAP_REVERSE:
        s_data["grade"] = GRADE_MAP_REVERSE[s_data["grade"]]

    s_data.pop("confirm_password")
    s_data["password"] = hash_password(data.password)
    s_data["student_code"] = generate_student_code()
    s_data["active_refresh_tokens"] = []
    await students.insert_one(s_data)
    return {"message": "Registered successfully. Please login."}


############ LOGIN ################

@app.post("/login", response_model=LoginResponseWithData)
async def login(response: Response, data: LoginRequest, students: AsyncIOMotorCollection = Depends(get_student_collection)):
    student = await students.find_one({"$or": [{"phone": data.identifier}, {"email": data.identifier}, {"student_code": data.identifier}]})
    if not student or not verify_password(data.password, student["password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    
    if len(student.get("active_refresh_tokens", [])) >= 30000000:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Max devices reached.")
    
    student_id = str(student["_id"])
    access_token = create_access_token(student_id)
    refresh_token, refresh_expire = create_refresh_token(student_id)

    await students.update_one({"_id": student["_id"]}, {"$push": {"active_refresh_tokens": refresh_token}})

    response.set_cookie(
        "refresh_token",
        refresh_token,
        expires=refresh_expire,
        httponly=True,
        secure=True,
        samesite="none"
    )
    
    student = format_student_grade(student)
    student_info = StudentProfileResponse(**student)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "data": student_info
    }

############ LOGOUT ################

@app.post("/logout")
async def logout(response: Response, request: Request, student_collection: AsyncIOMotorCollection = Depends(get_student_collection), blacklist: AsyncIOMotorCollection = Depends(get_token_blacklist_collection)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active session.")
    payload = decode_token(refresh_token)
    if payload and (student_id := payload.get("sub")):
        await student_collection.update_one({"_id": ObjectId(student_id)}, {"$pull": {"active_refresh_tokens": refresh_token}})
        expire_time = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
        await blacklist.insert_one({"token": refresh_token, "expire_at": expire_time})
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}


############ REFRESH TOKEN ################

@app.post("/token/refresh", response_model=RefreshTokenResponse)
async def refresh(request: Request, response: Response, student_collection: AsyncIOMotorCollection = Depends(get_student_collection), blacklist: AsyncIOMotorCollection = Depends(get_token_blacklist_collection)):
    old_refresh_token = request.cookies.get("refresh_token")
    if not old_refresh_token: raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token missing")
    if await blacklist.find_one({"token": old_refresh_token}): raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session logged out")
    payload = decode_token(old_refresh_token)
    if not payload or not (student_id := payload.get("sub")): raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    student = await student_collection.find_one({"_id": ObjectId(student_id)})
    if not student or old_refresh_token not in student.get("active_refresh_tokens", []): raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token no longer valid")
    new_access_token, (new_refresh_token, new_refresh_expire) = create_access_token(student_id), create_refresh_token(student_id)
    await student_collection.update_one({"_id": ObjectId(student_id)}, {"$pull": {"active_refresh_tokens": old_refresh_token}})
    await student_collection.update_one({"_id": ObjectId(student_id)}, {"$push": {"active_refresh_tokens": new_refresh_token}})
    response.set_cookie("refresh_token", new_refresh_token, expires=new_refresh_expire, httponly=True, secure=True, samesite="none")
    return {"access_token": new_access_token, "refresh_token": new_refresh_token}

############ FORGET PASS ################

@app.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, background_tasks: BackgroundTasks, students: AsyncIOMotorCollection = Depends(get_student_collection), reset_codes: AsyncIOMotorCollection = Depends(get_password_reset_collection)):
    student = await students.find_one({"email": data.email})
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email is not registered."
        )

    code = str(random.randint(10000, 99999))
    hashed_code = hash_password(code)
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    await reset_codes.update_one(
        {"email": data.email},
        {"$set": {"code": hashed_code, "expire_at": expire_at}},
        upsert=True
    )

    background_tasks.add_task(send_password_reset_email, data.email, code)
    
    return {"message": "A password reset code has been sent to your email."}

############ Verify code ################

@app.post("/verify-reset-code")
async def verify_reset_code(data: VerifyResetCodeRequest, reset_codes: AsyncIOMotorCollection = Depends(get_password_reset_collection)):
    reset_request = await reset_codes.find_one({"email": data.email})
    if not reset_request or not verify_password(data.code, reset_request["code"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset code.")
    await reset_codes.delete_one({"_id": reset_request["_id"]})
    permission_token = create_password_reset_token(data.email, "reset_password_permission", 5)
    return {"message": "Code verified.", "reset_token": permission_token}

############ Reset PASS ################

@app.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, students: AsyncIOMotorCollection = Depends(get_student_collection)):
    payload = decode_token(data.token)
    if not payload or payload.get("scope") != "reset_password_permission": raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token.")
    email = payload.get("sub")
    if not email: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid token payload.")
    new_hashed_password = hash_password(data.new_password)
    result = await students.update_one({"email": email}, {"$set": {"password": new_hashed_password, "active_refresh_tokens": []}})
    if result.matched_count == 0: raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found.")
    return {"message": "Password reset successfully."}

############ Get prof ################

@app.get("/student/profile", response_model=StudentProfileResponse)
async def get_student_profile(current_student: dict = Depends(get_current_student)):
    current_student = format_student_grade(current_student)
    return StudentProfileResponse(**current_student)

############ POST prof ################

@app.put("/student/profile/edit")
async def edit_profile(data: StudentEditRequest, current_student: dict = Depends(get_current_student), student_collection: AsyncIOMotorCollection = Depends(get_student_collection)):
    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data to update")

    if "grade" in update_data and update_data["grade"] in GRADE_MAP_REVERSE:
        update_data["grade"] = GRADE_MAP_REVERSE[update_data["grade"]]

    if "password" in update_data and update_data["password"]:
        update_data["password"] = hash_password(update_data["password"])
    else:
        update_data.pop("password", None)
        
    await student_collection.update_one({"_id": current_student["_id"]}, {"$set": update_data})
    updated_doc = await student_collection.find_one({"_id": current_student["_id"]})
    
    updated_doc = format_student_grade(updated_doc)
    
    response_data = StudentProfileResponse(**updated_doc).dict()
    response_data.pop("password", None)
    return {"message": "Profile updated", "student": response_data}

######################## Receipts ############################
############ Create rec ################

@app.post("/receipts", response_model=ReceiptResponse)
async def add_receipt(receipt_data: ReceiptCreate, student_collection: AsyncIOMotorCollection = Depends(get_student_collection), receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection), _: dict = Depends(get_current_student)):
    target_student = await student_collection.find_one({"student_code": receipt_data.student_code})
    if not target_student: raise HTTPException(status.HTTP_404_NOT_FOUND, f"Student with code '{receipt_data.student_code}' not found.")
    student_id = str(target_student["_id"])
    new_receipt_data = receipt_data.dict()
    new_receipt_data.update({"student_id": student_id, "created_at": datetime.now(timezone.utc)})
    result = await receipt_collection.insert_one(new_receipt_data)
    created_receipt = await receipt_collection.find_one({"_id": result.inserted_id})
    created_receipt["_id"] = str(created_receipt["_id"])
    return created_receipt

############ Get rec ################

@app.get("/receipts/{student_code}", response_model=List[ReceiptResponse])
async def get_all_receipts_for_student(student_code: str, receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection), _: dict = Depends(get_current_student)):
    receipts_cursor = receipt_collection.find({"student_code": student_code})
    receipts_list = await receipts_cursor.to_list(length=1000)
    for receipt in receipts_list: receipt["_id"] = str(receipt["_id"])
    return receipts_list

# --- EDUCATIONAL CONTENT ENDPOINTS ---
############ GET Home Page chapters ################

@app.get("/homepage/{year}/{term}/{language}/{subject}", response_model=List[LessonResponseV2])
async def get_homepage_chapters(year: str, term: str, language: str, subject: str, edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)):
    content_doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not content_doc or year not in content_doc["content"] or term not in content_doc["content"][year] or language not in content_doc["content"][year][term] or subject not in content_doc["content"][year][term][language]:
        return []

    content = content_doc["content"][year][term][language][subject]
    lessons_data = content.get("lessons", {})
    chapters_data = content.get("chapters", {})
    
    lessons = []
    for lesson_id, lesson_data in lessons_data.items():
        price_str = lesson_data.get("price", "0 جنية").split()[0]
        try:
            price_val = float(price_str)
        except (ValueError, IndexError):
            price_val = 0.0

        chapter_title = chapters_data.get(str(lesson_data.get("chapter_id")), {}).get("title")

        lessons.append(LessonResponseV2(
            id=str(lesson_id),
            title=lesson_data.get("title"),
            description=lesson_data.get("description", ""),
            vimeo_embed_src=lesson_data.get("vimeo_embed_src"),
            image_url=lesson_data.get("image_url"),
            price=price_val,
            hours=lesson_data.get("hours", 0),
            lecture=lesson_data.get("lecture", ""),
            course=f"{chapter_title} ({lesson_data.get('chapter_id')})" if chapter_title else ""
        ))
    return lessons

############ GET chapters lessons ################

@app.get("/chapters/{chapter_id}", response_model=List[LessonResponseV2])
async def get_chapter_lessons(chapter_id: int, edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)):
    lessons = []
    found_lessons = False
    chapter_title = None

    edu_doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not edu_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Educational content not found.")
    content = edu_doc.get("content", {})
    
    # Find the chapter title first
    for year_data in content.values():
        for term_data in year_data.values():
            for lang_data in term_data.values():
                for subject_data in lang_data.values():
                    if str(chapter_id) in subject_data.get("chapters", {}):
                        chapter_title = subject_data["chapters"][str(chapter_id)]["title"]
                        break
                if chapter_title:
                    break
            if chapter_title:
                break
        if chapter_title:
            break
            
    if not chapter_title:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapter not found.")

    # Iterate through content to find lessons for the specified chapter
    for year in content.values():
        for term in year.values():
            for language in term.values():
                for subject in language.values():
                    for lesson_id, lesson_data in subject.get("lessons", {}).items():
                        if lesson_data.get("chapter_id") == chapter_id:
                            found_lessons = True
                            # Safely extract data with default values for missing keys
                            price_str = lesson_data.get("price", "0 جنية").split()[0]
                            try:
                                price_val = float(price_str)
                            except (ValueError, IndexError):
                                price_val = 0.0
                            
                            # Use the same logic for the lesson's course and lecture
                            course_string = f"{chapter_title} ({chapter_id})"
                            lecture_string = f"Lecture {lesson_id}"

                            lessons.append(LessonResponseV2(
                                id=str(lesson_id),
                                title=lesson_data.get("title"),
                                description=lesson_data.get("description", ""),
                                vimeo_embed_src=lesson_data.get("vimeo_embed_src"),
                                image_url=lesson_data.get("image_url"),
                                price=price_val,
                                hours=lesson_data.get("hours", 0),
                                lecture=lecture_string,
                                course=course_string
                            ))

    if not found_lessons:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapter has no lessons.")
        
    return lessons

# --- GET Lesson Details
@app.get("/lessons/{lesson_id}", response_model=LessonResponseV2)
async def get_lesson_details(lesson_id: int, edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)):
    edu_doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not edu_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Educational content not found.")
    content = edu_doc.get("content", {})
    
    lesson_summary = None
    chapter_title = None

    for year in content.values():
        for term in year.values():
            for language in term.values():
                for subject in language.values():
                    if str(lesson_id) in subject.get("lessons", {}): 
                        lesson_summary = subject["lessons"][str(lesson_id)]
                        chapter_title = subject.get("chapters", {}).get(str(lesson_summary.get("chapter_id")), {}).get("title")
                        break
                if lesson_summary:
                    break
            if lesson_summary:
                break
    
    if not lesson_summary: 
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found.")

    price_str = lesson_summary.get("price", "0 جنية").split()[0]
    try:
        price_val = float(price_str)
    except (ValueError, IndexError):
        price_val = 0.0
    
    course_string = f"{chapter_title} ({lesson_summary.get('chapter_id')})" if chapter_title else ""
    lecture_string = f"Lecture {lesson_id}"

    return LessonResponseV2(
        id=str(lesson_id),
        title=lesson_summary.get("title"),
        description=lesson_summary.get("description", ""),
        vimeo_embed_src=lesson_summary.get("vimeo_embed_src"),
        image_url=lesson_summary.get("image_url"),
        price=price_val,
        hours=lesson_summary.get("hours", 0),
        lecture=lecture_string,
        course=course_string
    )




############ GET Free Chapters ################
@app.get("/homepage/{year}/{term}/{language}/{subject}/free", response_model=List[LessonResponseV2])
async def get_free_chapters(year: str, term: str, language: str, subject: str, edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)):
    content_doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not content_doc or year not in content_doc["content"] or term not in content_doc["content"][year] or language not in content_doc["content"][year][term] or subject not in content_doc["content"][year][term][language]:
        return []

    content = content_doc["content"][year][term][language][subject]
    lessons_data = content.get("lessons", {})
    chapters_data = content.get("chapters", {})

    free_lessons = []
    for lesson_id, lesson_data in lessons_data.items():
        if lesson_data.get('isFree', False):
            price_str = lesson_data.get("price", "0 جنية").split()[0]
            try:
                price_val = float(price_str)
            except (ValueError, IndexError):
                price_val = 0.0
            
            chapter_title = chapters_data.get(str(lesson_data.get("chapter_id")), {}).get("title")

            free_lessons.append(LessonResponseV2(
                id=str(lesson_id),
                title=lesson_data.get("title"),
                description=lesson_data.get("description", ""),
                vimeo_embed_src=lesson_data.get("vimeo_embed_src"),
                image_url=lesson_data.get("image_url"),
                price=price_val,
                hours=lesson_data.get("hours", 0),
                lecture=lesson_data.get("lecture", ""),
                course=f"{chapter_title} ({lesson_data.get('chapter_id')})" if chapter_title else ""
            ))
    return free_lessons

############ GET Paid Chapters ################
@app.get("/homepage/{year}/{term}/{language}/{subject}/paid", response_model=List[LessonResponseV2])
async def get_paid_chapters(year: str, term: str, language: str, subject: str, edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)):
    content_doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not content_doc or year not in content_doc["content"] or term not in content_doc["content"][year] or language not in content_doc["content"][year][term] or subject not in content_doc["content"][year][term][language]:
        return []

    content = content_doc["content"][year][term][language][subject]
    lessons_data = content.get("lessons", {})
    chapters_data = content.get("chapters", {})

    paid_lessons = []
    for lesson_id, lesson_data in lessons_data.items():
        if not lesson_data.get('isFree', False):
            price_str = lesson_data.get("price", "0 جنية").split()[0]
            try:
                price_val = float(price_str)
            except (ValueError, IndexError):
                price_val = 0.0

            chapter_title = chapters_data.get(str(lesson_data.get("chapter_id")), {}).get("title")

            paid_lessons.append(LessonResponseV2(
                id=str(lesson_id),
                title=lesson_data.get("title"),
                description=lesson_data.get("description", ""),
                vimeo_embed_src=lesson_data.get("vimeo_embed_src"),
                image_url=lesson_data.get("image_url"),
                price=price_val,
                hours=lesson_data.get("hours", 0),
                lecture=lesson_data.get("lecture", ""),
                course=f"{chapter_title} ({lesson_data.get('chapter_id')})" if chapter_title else ""
            ))
    return paid_lessons



# --- BOOKS ENDPOINT ---
@app.get("/books", response_model=List[BookResponse])
async def get_books(books_collection: AsyncIOMotorCollection = Depends(get_books_collection)):
    books = await books_collection.find().to_list(1000)
    # Pydantic will handle the mapping from _id to id if necessary
    return books

@app.post("/dashboard/buy-item", response_model=ReceiptResponse)
async def buy_item(
    purchase_data: ItemPurchaseRequest,
    current_student: dict = Depends(get_current_student),
    receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    """
    Simulates a student buying an item. In a real app, this would
    involve a payment gateway. Here, it just creates a receipt.
    """
    # Fetch item details from the database
    item_details = await find_item_in_content_by_id(int(purchase_data.item_id))
    if not item_details:
        raise HTTPException(status_code=404, detail=f"{purchase_data.item_type} with ID {purchase_data.item_id} not found")

    # Create a receipt to log the "purchase"
    new_receipt_data = {
        "student_id": str(current_student["_id"]),
        "student_code": current_student["student_code"],
        "receipt_type": "package_purchase",  # Designates a content purchase
        "item_id": purchase_data.item_id,
        "amount": float(item_details.get("price", "0 EGP").split()[0]),
        "description": f"Purchase of {purchase_data.item_type}: {item_details.get('title')}",
        "created_at": datetime.now(timezone.utc)
    }

    result = await receipt_collection.insert_one(new_receipt_data)
    created_receipt = await receipt_collection.find_one({"_id": result.inserted_id})
    created_receipt["_id"] = str(created_receipt["_id"])
    return created_receipt


@app.get("/dashboard/my-chapters", response_model=List[LessonResponseV2])
async def get_my_chapters(
    current_student: dict = Depends(get_current_student),
    receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    """
    Gets all lessons belonging to the chapters the authenticated student
    has paid for by checking their receipts.
    """
    receipts_cursor = receipt_collection.find({
        "student_code": current_student["student_code"],
        "receipt_type": "package_purchase"
    })
    receipts = await receipts_cursor.to_list(length=1000)
    purchased_chapter_ids = {int(r["item_id"]) for r in receipts}

    edu_doc = await edu_collection.find_one({"content": {"$exists": True}})
    if not edu_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Educational content not found.")
    content = edu_doc.get("content", {})

    my_lessons = []
    for year in content.values():
        for term in year.values():
            for language in term.values():
                for subject in language.values():
                    # Check if the lessons exist in the subject dictionary
                    for lesson_id, lesson_data in subject.get("lessons", {}).items():
                        # The database stores IDs as strings, so convert for comparison
                        if int(lesson_data.get("chapter_id")) in purchased_chapter_ids:
                            # Safely extract the price and convert to float
                            price_str = lesson_data.get("price", "0 جنية").split()[0]
                            try:
                                price_val = float(price_str)
                            except (ValueError, IndexError):
                                price_val = 0.0

                            # Get the chapter title for the 'course' field
                            chapter_title = subject.get("chapters", {}).get(str(lesson_data.get("chapter_id")), {}).get("title")

                            # Append the lesson to the list using the desired schema
                            my_lessons.append(LessonResponseV2(
                                id=str(lesson_id),
                                title=lesson_data.get("title"),
                                description=lesson_data.get("description", ""),
                                vimeo_embed_src=lesson_data.get("vimeo_embed_src"),
                                image_url=lesson_data.get("image_url"),
                                price=price_val,
                                hours=lesson_data.get("hours", 0),
                                lecture=lesson_data.get("lecture", ""),
                                course=f"{chapter_title} ({lesson_data.get('chapter_id')})" if chapter_title else ""
                            ))
                            
    return my_lessons

@app.get("/dashboard/my-tests", response_model=List[TestResultResponse])
async def get_my_tests(
    current_student: dict = Depends(get_current_student),
    tests_collection: AsyncIOMotorCollection = Depends(get_mock_test_results_collection)
):
    """
    Gets a list of all tests the student has completed.
    This currently uses mock data.
    """
    student_code = current_student.get("student_code")
    # In a real app, you would query your database for test results.
    tests = await tests_collection.find({"student_code": student_code}).to_list(1000)
    return tests



@app.post("/dashboard/add-test-result", response_model=TestResultResponse)
async def add_test_result(
    test_data: AddTestResultRequest,
    current_student: dict = Depends(get_current_student),
    tests_collection: AsyncIOMotorCollection = Depends(get_mock_test_results_collection)
):
    """
    Adds a new test result to the student's record.
    This currently uses mock data.
    """
    student_code = current_student.get("student_code")
    if not student_code:
        raise HTTPException(status_code=403, detail="Student code not found for current user.")

    # In a real app, you would save this to your database.
    # Here, we add it to our mock dictionary.
    
    # Get the count of existing test results for this student to determine the new ID
    # This is a simplified approach for the mock data, a real database would have its own ID mechanism
    last_test = await tests_collection.find({"student_code": student_code}).sort([("id", -1)]).limit(1).to_list(1)
    new_test_id = (last_test[0]["id"] + 1) if last_test else 1

    new_test_result = {
        "id": new_test_id,
        "test_name": test_data.test_name,
        "score": test_data.score,
        "date_taken": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "review_link": f"/api/tests/review/{new_test_id}",
        "download_link": f"/api/tests/download/{new_test_id}",
        "student_code": student_code
    }
    
    await tests_collection.insert_one(new_test_result)
    
    return TestResultResponse(**new_test_result)

@app.post("/dashboard/favorites/add", status_code=status.HTTP_201_CREATED)
async def add_favorite_video(
    fav_request: FavoriteVideoRequest,
    current_student: dict = Depends(get_current_student),
    favorites_collection: AsyncIOMotorCollection = Depends(get_favorite_videos_collection),
    videos_collection: AsyncIOMotorCollection = Depends(get_mock_videos_collection)
):
    """Adds a video to the current student's favorites."""
    video_id = fav_request.video_id
    if not await videos_collection.find_one({"id": video_id}):
        raise HTTPException(status_code=404, detail="Video not found")

    student_id = current_student["_id"]

    # Prevent duplicate entries
    existing_fav = await favorites_collection.find_one({"student_id": student_id, "video_id": video_id})
    if existing_fav:
        return {"message": "Video is already in favorites."}

    await favorites_collection.insert_one({
        "student_id": student_id,
        "video_id": video_id,
        "added_at": datetime.now(timezone.utc)
    })
    return {"message": "Video added to favorites."}


@app.get("/dashboard/favorites", response_model=List[VideoResponse])
async def get_my_favorite_videos(
    current_student: dict = Depends(get_current_student),
    favorites_collection: AsyncIOMotorCollection = Depends(get_favorite_videos_collection),
    videos_collection: AsyncIOMotorCollection = Depends(get_mock_videos_collection)
):
    """Gets a list of the current student's favorite videos."""
    student_id = current_student["_id"]
    
    favorites_cursor = favorites_collection.find({"student_id": student_id})
    favorite_records = await favorites_cursor.to_list(length=1000)
    
    # Get the full details for each favorited video ID from the database
    video_ids = [fav["video_id"] for fav in favorite_records]
    
    favorite_videos = await videos_collection.find({"id": {"$in": video_ids}}).to_list(1000)
    
    return favorite_videos

# --- PARENT PORTAL ENDPOINT ---

@app.post("/parent/dashboard", response_model=ParentDashboardResponse)
async def get_parent_dashboard(
    login_data: ParentLoginRequest,
    student_collection: AsyncIOMotorCollection = Depends(get_student_collection),
    receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection),
    tests_collection: AsyncIOMotorCollection = Depends(get_mock_test_results_collection),
    edu_collection: AsyncIOMotorCollection = Depends(get_educational_content_collection)
):
    """
    Provides a comprehensive dashboard for a parent by verifying
    the student's phone and parent's phone number.
    """
    # 1. Find the student using both phone numbers for verification
    student = await student_collection.find_one({
        "phone": login_data.student_phone,
        "parent_phone": login_data.parent_phone
    })

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching student found for the provided phone numbers."
        )

    student_code = student.get("student_code")

    # 2. Get the student's test results from the database
    tests_cursor = tests_collection.find({"student_code": student_code})
    test_results = await tests_cursor.to_list(length=1000)

    # 3. Get the student's purchased chapters from the database
    receipts_cursor = receipt_collection.find({
        "student_code": student_code,
        "receipt_type": "package_purchase"
    })
    receipts = await receipts_cursor.to_list(length=1000)
    purchased_item_ids = {int(r["item_id"]) for r in receipts}

    edu_doc = await edu_collection.find_one({"content": {"$exists": True}})
    purchased_chapters = []
    if edu_doc:
        content = edu_doc.get("content", {})
        for year in content.values():
            for term in year.values():
                for language in term.values():
                    for subject in language.values():
                        for cid, cdata in subject.get("chapters", {}).items():
                            if int(cid) in purchased_item_ids:
                                purchased_chapters.append(
                                    ChapterSummaryResponse(id=int(cid), image=courseImg, variant="chapter", **cdata)
                                )
    
    student = format_student_grade(student)
    # 4. Assemble and return the complete dashboard response
    return ParentDashboardResponse(
        student_info=StudentProfileResponse(**student),
        purchased_chapters=purchased_chapters,
        test_results=test_results
    )

# --- TESTING PAGE ---
@app.get("/try", response_class=FileResponse)
def get_test_frontend():
    return FileResponse("try.html", media_type="text/html")

@app.get("/admin_try", response_class=FileResponse)
def get_admin_test_frontend():
    return FileResponse("admin_try.html", media_type="text/html")