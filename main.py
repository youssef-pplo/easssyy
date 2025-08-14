from fastapi import FastAPI, HTTPException, Depends, status, Request ,Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from database import SessionLocal, engine, Base
from models import Student
from schemas import RegisterRequest, LoginRequest, TokenResponse , StudentEditRequest , StudentProfileResponse

from utils import create_access_token, create_refresh_token, verify_password
from pydantic import BaseModel
from jose import JWTError, jwt
from typing import Optional
import requests
from passlib.context import CryptContext
import random
import string
# -------------------------
# Configuration / Constants
# -------------------------
SECRET_KEY = "Ea$yB1o"    # <-- keep this value and make sure utils uses the same secret!
ALGORITHM = "HS256"


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# External OTP PHP endpoints (used on register and login verification)
OTP_SEND_URL = "https://easybio-drabdelrahman.com/otp-system/send_otp.php"
OTP_STATUS_URL = "https://easybio-drabdelrahman.com/otp-system/status.php"
# -------------------------

# Create DB tables (no-op if already created)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS — preserved exactly as requested
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# OAuth2 scheme for extracting tokens from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# -------------------------
# Helper: decode token safely
# -------------------------
def decode_token_or_none(token: str):
    """
    Decode JWT and return payload dict, or None on failure.
    Uses SECRET_KEY and ALGORITHM defined above.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None



#--------------------------
# gen stu code 
# -------------------------


def generate_student_code(length=8):
    # generates a random alphanumeric code of given length
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
 
# -------------------------
# Register endpoint
# -------------------------
@app.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(Student).filter((Student.phone == data.phone) | (Student.email == data.email)).first():
        raise HTTPException(status_code=400, detail="Phone or Email already exists")
    
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    hashed_password = bcrypt.hash(data.password)
    new_student_code = generate_student_code()

    student = Student(
        **data.dict(exclude={"password", "confirm_password"}),
        password=hashed_password,
        student_code=new_student_code,
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    # Send OTP to email
    try:
        requests.post(OTP_SEND_URL, data={"email": data.email})
    except Exception as e:
        print("Failed to send OTP:", e)

    return {
        "message": "Registered successfully. Please verify your email.",
        "access_token": create_access_token(student.id),
        "refresh_token": create_refresh_token(student.id),
        "student": {
            "id": student.id,
            "student_code": student.student_code,
            "name": student.name,
            "phone": student.phone,
            "email": student.email,
            "lang": student.lang,
            "parent_phone": student.parent_phone,
        }
    }



# -------------------------
# Login endpoint
# -------------------------
@app.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        (Student.phone == data.identifier) |
        (Student.email == data.identifier) |
        (Student.student_code == data.identifier)
    ).first()

    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        if not verify_password(data.password, student.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception as e:
        print("Password verification failed:", e)
        raise HTTPException(status_code=500, detail="Internal server error")

    # تحقق من أن الإيميل مُوثق (إذا فيه إيميل)
    if student.email:
        try:
            resp = requests.post(OTP_STATUS_URL, data={"email": student.email}, timeout=5)
            resp.raise_for_status()  # يرمي استثناء لو الحالة مش 200
            status_json = resp.json()
            if not status_json.get("verified", False):
                raise HTTPException(status_code=403, detail="Email not verified")
        except HTTPException:
            raise  # إعادة رفع الخطأ للعميل
        except Exception as e:
            print("OTP status check failed:", e)
            raise HTTPException(status_code=500, detail="Failed to verify email")

    access_token = create_access_token(student.id)
    refresh_token = create_refresh_token(student.id)

    return {"access_token": access_token, "refresh_token": refresh_token}


# -------------------------
# Refresh endpoint
# -------------------------
class RefreshRequest(BaseModel):
    refresh_token: str

@app.post("/token/refresh")
def refresh_token(data: RefreshRequest):
    """
    Accepts JSON body { "refresh_token": "<token>" }.
    Validates & decodes the refresh token, issues a new access token.
    """
    token = data.refresh_token
    payload = decode_token_or_none(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    # convert sub to int when possible (your tokens use student.id)
    try:
        student_id = int(sub)
    except Exception:
        student_id = sub

    # You may want to check a revocation DB here — omitted for brevity
    new_access = create_access_token(student_id)
    new_refresh = create_refresh_token(student_id)  # rotate refresh token if desired

    return {"access_token": new_access, "refresh_token": new_refresh}

# -------------------------
# Dependency: current student
# -------------------------
def get_current_student(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Student:
    """
    Validates Authorization Bearer token and returns Student object.
    Raises 401 if token invalid, 404 if student not found.
    """
    payload = decode_token_or_none(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    # convert to int if possible
    try:
        student_id = int(sub)
    except Exception:
        student_id = sub

    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student

# -------------------------
# Student profile endpoint
# -------------------------
class StudentProfileResponse(BaseModel):
    student_code: Optional[str]
    name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    username: Optional[str]
    parent_phone: Optional[str]
    city: Optional[str]
    lang: Optional[str]
    grade: Optional[str]
    password: str

@app.get("/student/profile", response_model=StudentProfileResponse)
def get_student_profile(current_student: Student = Depends(get_current_student)):
    """
    Returns the authenticated student's profile. Missing fields become null.
    The password is masked.
    """
    return StudentProfileResponse(
        student_code=getattr(current_student, "student_code", None),
        name=getattr(current_student, "name", None),
        phone=getattr(current_student, "phone", None),
        email=getattr(current_student, "email", None),
        username=getattr(current_student, "student_code", None),
        parent_phone=getattr(current_student, "parent_phone", None),
        city=getattr(current_student, "city", None),
        lang=getattr(current_student, "lang", None),
        grade=getattr(current_student, "grade", None) or getattr(current_student, "year_of_study", None),
        password="****"
    )



#--
# edit 
#--
 

@app.put("/student/profile/edit")
def edit_profile(
    data: StudentEditRequest,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided to update")

    for key, value in update_data.items():
        setattr(current_student, key, value)

    db.commit()
    db.refresh(current_student)

    return {
        "message": "Profile updated successfully",
        "student": {
            "student_code": current_student.student_code,
            "name": current_student.name,
            "email": current_student.email,
            "phone": current_student.phone,
            "username": getattr(current_student, "username", None),
            "parent_phone": current_student.parent_phone,
            "city": current_student.city,
            "lang": current_student.lang,
            "grade": current_student.grade,
        }
    }

# -------------------------
# Health / debug route
# -------------------------
@app.get("/")
def root():
    return {"status": "ok"}
