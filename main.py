# main.py
from fastapi import FastAPI, HTTPException, Depends, status, Response, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse
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

from database import (
    connect_to_mongo, close_mongo_connection, get_student_collection,
    get_token_blacklist_collection, get_receipt_collection,
    get_password_reset_collection
)
from schemas import (
    RegisterRequest, LoginRequest, TokenResponse, RefreshTokenResponse,
    StudentEditRequest, StudentProfileResponse,
    ReceiptCreate, ReceiptResponse,
    ForgotPasswordRequest, VerifyResetCodeRequest, ResetPasswordRequest,
    ChapterSummaryResponse, LessonSummaryResponse, LessonDetailResponse
)
from motor.motor_asyncio import AsyncIOMotorCollection

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
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
    allow_origins=["*", "http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# --- NEW COMPREHENSIVE MOCK DATABASE FOR EDUCATIONAL CONTENT ---
courseImg = "https://via.placeholder.com/200"
EDUCATIONAL_CONTENT = {
    "1": { # Year 1
        "term1": {
            "arabic": {
                "biology": {
                    "chapters": {
                        101: {"title": "الفصل الأول: الأساس الكيميائي للحياة", "price": "150 جنية"},
                        102: {"title": "الفصل الثاني: الخلية", "price": "170 جنية"},
                    },
                    "lessons": {
                        10101: {"chapter_id": 101, "title": "مقدمة أولى ثانوي", "price": "مجانا", "isFree": True},
                        10102: {"chapter_id": 101, "title": "التركيب الكيميائي", "price": "75 جنية", "isFree": False},
                        10201: {"chapter_id": 102, "title": "النظرية الخلوية", "price": "85 جنية", "isFree": False},
                    },
                    "lesson_details": {
                        10101: {"subject": "أولى ثانوي - ترم أول", "duration": "ساعة", "exams": "لا يوجد", "questions": "10 أسئلة"},
                        10102: {"subject": "أولى ثانوي - ترم أول", "duration": "ساعتان", "exams": "1 امتحان", "questions": "30 سؤال"},
                        10201: {"subject": "أولى ثانوي - ترم أول", "duration": "ساعة ونصف", "exams": "1 امتحان", "questions": "40 سؤال"},
                    }
                }
            },
            "english": {
                "biology": {
                    "chapters": {
                        111: {"title": "Chapter 1: Chemical Basis of Life", "price": "150 EGP"},
                        112: {"title": "Chapter 2: The Cell", "price": "170 EGP"},
                    },
                    "lessons": {
                        11101: {"chapter_id": 111, "title": "Intro for 1st Year", "price": "Free", "isFree": True},
                        11102: {"chapter_id": 111, "title": "Chemical Composition", "price": "75 EGP", "isFree": False},
                        11201: {"chapter_id": 112, "title": "Cell Theory", "price": "85 EGP", "isFree": False},
                    },
                     "lesson_details": {
                        11101: {"subject": "1st Year - Term 1", "duration": "1 hour", "exams": "None", "questions": "10 questions"},
                        11102: {"subject": "1st Year - Term 1", "duration": "2 hours", "exams": "1 exam", "questions": "30 questions"},
                        11201: {"subject": "1st Year - Term 1", "duration": "1.5 hours", "exams": "1 exam", "questions": "40 questions"},
                    }
                }
            }
        },
        "term2": { # Year 1, Term 2
            "arabic": {
                "biology": {
                    "chapters": {
                        121: {"title": "الفصل الثالث: الوراثة", "price": "160 جنية"},
                    },
                    "lessons": {
                        12101: {"chapter_id": 121, "title": "قوانين مندل", "price": "80 جنية", "isFree": False},
                    },
                    "lesson_details": {
                        12101: {"subject": "أولى ثانوي - ترم ثاني", "duration": "ساعتان", "exams": "1 امتحان", "questions": "35 سؤال"},
                    }
                }
            },
            "english": {
                 "biology": {
                    "chapters": {
                        131: {"title": "Chapter 3: Genetics", "price": "160 EGP"},
                    },
                    "lessons": {
                        13101: {"chapter_id": 131, "title": "Mendel's Laws", "price": "80 EGP", "isFree": False},
                    },
                    "lesson_details": {
                        13101: {"subject": "1st Year - Term 2", "duration": "2 hours", "exams": "1 exam", "questions": "35 questions"},
                    }
                }
            }
        }
    },
    "2": { # Year 2
        "term1": {
            "arabic": {
                "biology": {
                    "chapters": {
                        201: {"title": "الفصل الأول: التغذية والهضم", "price": "200 جنية"},
                        202: {"title": "الفصل الثاني: النقل", "price": "210 جنية"},
                    },
                    "lessons": {
                        20101: {"chapter_id": 201, "title": "التغذية الذاتية", "price": "مجانا", "isFree": True},
                        20201: {"chapter_id": 202, "title": "النقل في النبات", "price": "105 جنية", "isFree": False},
                    },
                    "lesson_details": {
                        20101: {"subject": "تانية ثانوي - ترم أول", "duration": "ساعة وربع", "exams": "لا يوجد", "questions": "15 سؤال"},
                        20201: {"subject": "تانية ثانوي - ترم أول", "duration": "ساعتان", "exams": "1 امتحان", "questions": "45 سؤال"},
                    }
                }
            },
            "english": {
                "biology": {
                    "chapters": {
                        211: {"title": "Chapter 1: Nutrition and Digestion", "price": "200 EGP"},
                    },
                    "lessons": {
                        21101: {"chapter_id": 211, "title": "Autotrophic Nutrition", "price": "Free", "isFree": True},
                    },
                    "lesson_details": {
                        21101: {"subject": "2nd Year - Term 1", "duration": "1.25 hours", "exams": "None", "questions": "15 questions"},
                    }
                }
            }
        },
        "term2": { # Year 2, Term 2
             "arabic": {
                "biology": {
                    "chapters": {
                        221: {"title": "الفصل الثالث: التنفس", "price": "190 جنية"},
                    },
                    "lessons": {
                        22101: {"chapter_id": 221, "title": "التنفس الخلوي", "price": "95 جنية", "isFree": False},
                    },
                    "lesson_details": {
                        22101: {"subject": "تانية ثانوي - ترم ثاني", "duration": "ساعتان", "exams": "1 امتحان", "questions": "50 سؤال"},
                    }
                }
            },
            "english": {
                "biology": {
                    "chapters": {
                        231: {"title": "Chapter 3: Respiration", "price": "190 EGP"},
                    },
                    "lessons": {
                        23101: {"chapter_id": 231, "title": "Cellular Respiration", "price": "95 EGP", "isFree": False},
                    },
                    "lesson_details": {
                        23101: {"subject": "2nd Year - Term 2", "duration": "2 hours", "exams": "1 exam", "questions": "50 questions"},
                    }
                }
            }
        }
    },
    "3": { # Year 3
        "term1": {
            "arabic": {
                "biology": {
                    "chapters": {
                        301: {"title": "الفصل الأول: الدعامة والحركة", "price": "280 جنية"},
                    },
                    "lessons": {
                        30101: {"chapter_id": 301, "title": "الدعامة في الكائنات الحية", "price": "140 جنية", "isFree": False},
                    },
                    "lesson_details": {
                        30101: {"subject": "ثالثة ثانوي - ترم أول", "duration": "3 ساعات", "exams": "2 امتحان", "questions": "90 سؤال"},
                    }
                }
            },
            "english": {
                 "biology": {
                    "chapters": {
                        311: {"title": "Chapter 1: Support and Movement", "price": "280 EGP"},
                    },
                    "lessons": {
                        31101: {"chapter_id": 311, "title": "Support in Living Organisms", "price": "140 EGP", "isFree": False},
                    },
                    "lesson_details": {
                        31101: {"subject": "3rd Year - Term 1", "duration": "3 hours", "exams": "2 exams", "questions": "90 questions"},
                    }
                }
            }
        },
        "term2": {
            "arabic": {
                "biology": {
                    "chapters": {
                        321: {"title": "الفصل الثالث: التكاثر", "price": "300 جنية"},
                        322: {"title": "الفصل الرابع: المناعة", "price": "320 جنية"},
                    },
                    "lessons": {
                        32101: {"chapter_id": 321, "title": "طرق التكاثر", "price": "150 جنية", "isFree": False},
                        32201: {"chapter_id": 322, "title": "آليات عمل الجهاز المناعي", "price": "مجانا", "isFree": True},
                    },
                    "lesson_details": {
                        32101: {"subject": "ثالثة ثانوي - ترم ثاني", "duration": "3.5 ساعات", "exams": "2 امتحان", "questions": "100 سؤال"},
                        32201: {"subject": "ثالثة ثانوي - ترم ثاني", "duration": "ساعتان", "exams": "1 امتحان", "questions": "50 سؤال"},
                    }
                }
            },
            "english": {
                 "biology": {
                    "chapters": {
                        331: {"title": "Chapter 3: Reproduction", "price": "300 EGP"},
                        332: {"title": "Chapter 4: Immunity", "price": "320 EGP"},
                    },
                    "lessons": {
                        33101: {"chapter_id": 331, "title": "Methods of Reproduction", "price": "150 EGP", "isFree": False},
                        33201: {"chapter_id": 332, "title": "Immune System Mechanisms", "price": "Free", "isFree": True},
                    },
                    "lesson_details": {
                        33101: {"subject": "3rd Year - Term 2", "duration": "3.5 hours", "exams": "2 exams", "questions": "100 questions"},
                        33201: {"subject": "3rd Year - Term 2", "duration": "2 hours", "exams": "1 exam", "questions": "50 questions"},
                    }
                }
            }
        }
    }
}


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

# --- API Endpoints ---
@app.get("/")
def root(): return {"status": "ok"}
@app.post("/register")
async def register(data: RegisterRequest, students: AsyncIOMotorCollection = Depends(get_student_collection)):
    if await students.find_one({"$or": [{"phone": data.phone}, {"email": data.email}]}): raise HTTPException(status.HTTP_400_BAD_REQUEST, "Phone or Email already exists")
    if data.password != data.confirm_password: raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passwords do not match")
    s_data = data.dict()
    s_data.pop("confirm_password")
    s_data["password"] = hash_password(data.password)
    s_data["student_code"] = generate_student_code()
    s_data["active_refresh_tokens"] = []
    await students.insert_one(s_data)
    return {"message": "Registered successfully. Please login."}
@app.post("/login", response_model=TokenResponse)
async def login(response: Response, data: LoginRequest, students: AsyncIOMotorCollection = Depends(get_student_collection)):
    student = await students.find_one({"$or": [{"phone": data.identifier}, {"email": data.identifier}, {"student_code": data.identifier}]})
    if not student or not verify_password(data.password, student["password"]): raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if len(student.get("active_refresh_tokens", [])) >= 3: raise HTTPException(status.HTTP_403_FORBIDDEN, "Max devices reached.")
    student_id = str(student["_id"])
    access_token = create_access_token(student_id)
    refresh_token, refresh_expire = create_refresh_token(student_id)
    await students.update_one({"_id": student["_id"]}, {"$push": {"active_refresh_tokens": refresh_token}})
    response.set_cookie("refresh_token", refresh_token, expires=refresh_expire, httponly=True, secure=True, samesite="none")
    return {"access_token": access_token}
@app.post("/logout")
async def logout(response: Response, request: Request, student_collection: AsyncIOMotorCollection = Depends(get_student_collection), blacklist: AsyncIOMotorCollection = Depends(get_token_blacklist_collection)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token: raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active session.")
    payload = decode_token(refresh_token)
    if payload and (student_id := payload.get("sub")):
        await student_collection.update_one({"_id": ObjectId(student_id)}, {"$pull": {"active_refresh_tokens": refresh_token}})
        expire_time = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
        await blacklist.insert_one({"token": refresh_token, "expire_at": expire_time})
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}
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
@app.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, background_tasks: BackgroundTasks, students: AsyncIOMotorCollection = Depends(get_student_collection), reset_codes: AsyncIOMotorCollection = Depends(get_password_reset_collection)):
    if student := await students.find_one({"email": data.email}):
        code = str(random.randint(10000, 99999))
        hashed_code = hash_password(code)
        expire_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        await reset_codes.update_one({"email": data.email}, {"$set": {"code": hashed_code, "expire_at": expire_at}}, upsert=True)
        background_tasks.add_task(send_password_reset_email, data.email, code)
    return {"message": "If an account exists, a reset code has been sent."}
@app.post("/verify-reset-code")
async def verify_reset_code(data: VerifyResetCodeRequest, reset_codes: AsyncIOMotorCollection = Depends(get_password_reset_collection)):
    reset_request = await reset_codes.find_one({"email": data.email})
    if not reset_request or not verify_password(data.code, reset_request["code"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset code.")
    await reset_codes.delete_one({"_id": reset_request["_id"]})
    permission_token = create_password_reset_token(data.email, "reset_password_permission", 5)
    return {"message": "Code verified.", "reset_token": permission_token}
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
@app.get("/student/profile", response_model=StudentProfileResponse)
async def get_student_profile(current_student: dict = Depends(get_current_student)): return StudentProfileResponse(**current_student)
@app.put("/student/profile/edit")
async def edit_profile(data: StudentEditRequest, current_student: dict = Depends(get_current_student), student_collection: AsyncIOMotorCollection = Depends(get_student_collection)):
    update_data = data.dict(exclude_unset=True)
    if not update_data: raise HTTPException(status.HTTP_400_BAD_REQUEST, "No data to update")
    if "password" in update_data and update_data["password"]: update_data["password"] = hash_password(update_data["password"])
    else: update_data.pop("password", None)
    await student_collection.update_one({"_id": current_student["_id"]}, {"$set": update_data})
    updated_doc = await student_collection.find_one({"_id": current_student["_id"]})
    response_data = StudentProfileResponse(**updated_doc).dict()
    response_data.pop("password", None)
    return {"message": "Profile updated", "student": response_data}
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
@app.get("/receipts/{student_code}", response_model=List[ReceiptResponse])
async def get_all_receipts_for_student(student_code: str, receipt_collection: AsyncIOMotorCollection = Depends(get_receipt_collection), _: dict = Depends(get_current_student)):
    receipts_cursor = receipt_collection.find({"student_code": student_code})
    receipts_list = await receipts_cursor.to_list(length=1000)
    for receipt in receipts_list: receipt["_id"] = str(receipt["_id"])
    return receipts_list

# --- EDUCATIONAL CONTENT ENDPOINTS ---
@app.get("/homepage/{year}/{term}/{language}/{subject}", response_model=List[ChapterSummaryResponse])
async def get_homepage_chapters(year: str, term: str, language: str, subject: str):
    try:
        content = EDUCATIONAL_CONTENT[year][term][language][subject]
        chapters_data = content.get("chapters", {})
    except KeyError:
        return [] # Return empty list if content is not found
    response = [ChapterSummaryResponse(id=cid, image=courseImg, variant="chapter", **cdata) for cid, cdata in chapters_data.items()]
    return response
@app.get("/chapters/{chapter_id}", response_model=List[LessonSummaryResponse])
async def get_chapter_lessons(chapter_id: int):
    lessons = []
    for year in EDUCATIONAL_CONTENT.values():
        for term in year.values():
            for language in term.values():
                for subject in language.values():
                    for lesson_id, lesson_data in subject.get("lessons", {}).items():
                        if lesson_data.get("chapter_id") == chapter_id:
                            lessons.append(LessonSummaryResponse(id=lesson_id, image=courseImg, **lesson_data))
    if not lessons: raise HTTPException(status.HTTP_404_NOT_FOUND, "Chapter not found or has no lessons.")
    return lessons
@app.get("/lessons/{lesson_id}", response_model=LessonDetailResponse)
async def get_lesson_details(lesson_id: int):
    lesson_summary, lesson_details = None, None
    for year in EDUCATIONAL_CONTENT.values():
        for term in year.values():
            for language in term.values():
                for subject in language.values():
                    if lesson_id in subject.get("lessons", {}): lesson_summary = subject["lessons"][lesson_id]
                    if lesson_id in subject.get("lesson_details", {}): lesson_details = subject["lesson_details"][lesson_id]
    if not lesson_summary or not lesson_details: raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found.")
    full_lesson_data = {"id": lesson_id, "image": courseImg, **lesson_summary, **lesson_details}
    return LessonDetailResponse(**full_lesson_data)

# --- TESTING PAGE ---
@app.get("/try", response_class=HTMLResponse)
async def get_test_frontend():
    html_content = """
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>API Tester</title>
    <style>body{font-family:sans-serif;margin:40px;}.container{max-width:800px;margin:auto;}h2{border-bottom:1px solid #ccc;padding-bottom:5px;}form{display:flex;flex-direction:column;gap:10px;margin-bottom:20px;}input,button,select{padding:10px;font-size:16px;}button{cursor:pointer;background-color:#007bff;color:white;border:none;border-radius:5px;}pre{background-color:#eee;padding:15px;white-space:pre-wrap;word-wrap:break-word;}</style>
    </head><body><div class="container"><h1>API Tester</h1><div><h2>Tokens</h2><label>Access Token:</label><br><input type="text" id="accessToken" style="width:100%;"></div>
    
    <h2>Educational Content</h2>
    <form id="contentForm">
        <h3>Get Homepage Chapters</h3>
        <select id="year"><option value="1">1st Year</option><option value="2">2nd Year</option><option value="3">3rd Year</option></select>
        <select id="term"><option value="term1">Term 1</option><option value="term2">Term 2</option></select>
        <select id="language"><option value="arabic">Arabic</option><option value="english">English</option></select>
        <select id="subject"><option value="biology">Biology</option></select>
        <button type="submit">Get Chapters</button>
    </form>
    <form id="chapterForm"><h3>Get Lessons in a Chapter</h3><input type="number" id="chapterId" placeholder="Chapter ID (e.g., 101, 211, 321)"><button type="submit">Get Lessons</button></form>
    <form id="lessonForm"><h3>Get Lesson Details</h3><input type="number" id="lessonId" placeholder="Lesson ID (e.g., 10101, 22101, 33101)"><button type="submit">Get Details</button></form>

    <h2>User Management & Other APIs</h2>
    <form id="registerForm"><h3>Register</h3><input type="email" id="regEmail" placeholder="Email" value="user1@example.com"><input type="password" id="regPassword" placeholder="Password" value="password123"><input type="password" id="regConfirmPassword" placeholder="Confirm Password" value="password123"><input type="text" id="regName" placeholder="Name" value="Test User"><input type="text" id="regPhone" placeholder="Phone (unique)" value="111222333"><input type="text" id="regParentPhone" placeholder="Parent Phone" value="444555666"><input type="text" id="regCity" placeholder="City" value="Testville"><input type="text" id="regGrade" placeholder="Grade" value="11"><input type="text" id="regLang" placeholder="Language" value="en"><button type="submit">Register</button></form>
    <form id="loginForm"><h3>Login</h3><input type="text" id="loginIdentifier" placeholder="Email or Phone" value="user1@example.com"><input type="password" id="loginPassword" placeholder="Password" value="password123"><button type="submit">Login</button></form>
    
    <h2>Password Reset</h2>
    <form id="forgotPasswordForm"><h3>1. Request Reset Code</h3><input type="email" id="forgotEmail" placeholder="Enter registered email" value="user1@example.com"><button type="submit">Send Code</button></form>
    <form id="verifyCodeForm"><h3>2. Verify Code</h3><input type="email" id="verifyEmail" placeholder="Enter email again" value="user1@example.com"><input type="text" id="resetCode" placeholder="5-digit code from email"><button type="submit">Verify Code & Get Reset Token</button></form>
    <form id="resetPasswordForm"><h3>3. Reset Password</h3><input type="text" id="resetToken" placeholder="Reset Token from step 2"><input type="password" id="newPassword" placeholder="New Password"><button type="submit">Reset Password</button></form>

    <h2>Authenticated Actions</h2><button id="getProfileBtn">Get Profile</button><button id="refreshTokenBtn">Refresh Tokens</button><button id="logoutBtn" style="background-color:#dc3545;">Logout</button>
    <h2>Receipts</h2><form id="addReceiptForm"><h3>Add Receipt</h3><input type="text" id="receiptStudentCode" placeholder="Student Code"><select id="receiptType"><option value="package_purchase">Package Purchase</option><option value="balance_charge">Balance Charge</option></select><input type="text" id="itemId" placeholder="Item ID (e.g., 'PHYSICS_PKG_1')"><input type="number" id="receiptAmount" placeholder="Amount"><input type="text" id="receiptDesc" placeholder="Description"><button type="submit">Add Receipt</button></form><form id="getReceiptsForm"><h3>Get Receipts by Student Code</h3><input type="text" id="getReceiptsStudentCode" placeholder="Student Code"><button type="submit">Get Receipts</button></form>
    <h2>API Response</h2><pre id="responseOutput">Response will be shown here...</pre></div>
    <script>
        const responseOutput = document.getElementById('responseOutput');
        const accessTokenInput = document.getElementById('accessToken');
        const resetTokenInput = document.getElementById('resetToken');

        const apiCall = async (endpoint, method = 'GET', body = null) => {
            const headers = { 'Content-Type': 'application/json' };
            if (accessTokenInput.value) { headers['Authorization'] = `Bearer ${accessTokenInput.value}`; }
            try {
                const options = { method, headers, credentials: 'include' };
                if (body) options.body = JSON.stringify(body);
                const response = await fetch(endpoint, options);
                const data = await response.json();
                responseOutput.textContent = JSON.stringify(data, null, 2);
                if (data.access_token) { accessTokenInput.value = data.access_token; }
                if (data.reset_token) { resetTokenInput.value = data.reset_token; }
            } catch (error) { responseOutput.textContent = `Error: ${error.message}`; }
        };
        
        // Content Listeners
        document.getElementById('contentForm').addEventListener('submit', e => { e.preventDefault(); const year = document.getElementById('year').value; const term = document.getElementById('term').value; const language = document.getElementById('language').value; const subject = document.getElementById('subject').value; apiCall(`/homepage/${year}/${term}/${language}/${subject}`, 'GET'); });
        document.getElementById('chapterForm').addEventListener('submit', e => { e.preventDefault(); const chapterId = document.getElementById('chapterId').value; if (chapterId) apiCall(`/chapters/${chapterId}`, 'GET'); });
        document.getElementById('lessonForm').addEventListener('submit', e => { e.preventDefault(); const lessonId = document.getElementById('lessonId').value; if (lessonId) apiCall(`/lessons/${lessonId}`, 'GET'); });
        
        // User & Auth Listeners
        document.getElementById('registerForm').addEventListener('submit', e => { e.preventDefault(); apiCall('/register', 'POST', { email: document.getElementById('regEmail').value, password: document.getElementById('regPassword').value, confirm_password: document.getElementById('regConfirmPassword').value, name: document.getElementById('regName').value, phone: document.getElementById('regPhone').value, parent_phone: document.getElementById('regParentPhone').value, city: document.getElementById('regCity').value, grade: document.getElementById('regGrade').value, lang: document.getElementById('regLang').value, }); });
        document.getElementById('loginForm').addEventListener('submit', e => { e.preventDefault(); apiCall('/login', 'POST', { identifier: document.getElementById('loginIdentifier').value, password: document.getElementById('loginPassword').value, }); });
        document.getElementById('forgotPasswordForm').addEventListener('submit', e => { e.preventDefault(); apiCall('/forgot-password', 'POST', { email: document.getElementById('forgotEmail').value }); });
        document.getElementById('verifyCodeForm').addEventListener('submit', e => { e.preventDefault(); apiCall('/verify-reset-code', 'POST', { email: document.getElementById('verifyEmail').value, code: document.getElementById('resetCode').value }); });
        document.getElementById('resetPasswordForm').addEventListener('submit', e => { e.preventDefault(); apiCall('/reset-password', 'POST', { token: document.getElementById('resetToken').value, new_password: document.getElementById('newPassword').value }); });
        document.getElementById('getProfileBtn').addEventListener('click', () => apiCall('/student/profile', 'GET'));
        document.getElementById('refreshTokenBtn').addEventListener('click', () => apiCall('/token/refresh', 'POST'));
        document.getElementById('logoutBtn').addEventListener('click', () => { apiCall('/logout', 'POST'); accessTokenInput.value = ''; });
        
        // Receipt Listeners
        document.getElementById('addReceiptForm').addEventListener('submit', e => { e.preventDefault(); apiCall('/receipts', 'POST', { student_code: document.getElementById('receiptStudentCode').value, receipt_type: document.getElementById('receiptType').value, item_id: document.getElementById('itemId').value, amount: parseFloat(document.getElementById('receiptAmount').value), description: document.getElementById('receiptDesc').value, }); });
        document.getElementById('getReceiptsForm').addEventListener('submit', e => { e.preventDefault(); const studentCode = document.getElementById('getReceiptsStudentCode').value; if(studentCode) apiCall(`/receipts/${studentCode}`, 'GET'); });
    </script>
    </body></html>
    """
    return HTMLResponse(content=html_content)
