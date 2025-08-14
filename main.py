# main.py
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from passlib.hash import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional
import requests
import random
import string
from bson import ObjectId
from datetime import datetime, timedelta

# Import the student collection from our new database file
from database import student_collection
from schemas import RegisterRequest, LoginRequest, TokenResponse, StudentEditRequest, StudentProfileResponse

# --- Configuration ---
SECRET_KEY = "Ea$yB1o"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# --- External OTP URLs ---
OTP_SEND_URL = "https://easybio-drabdelrahman.com/otp-system/send_otp.php"
OTP_STATUS_URL = "https://easybio-drabdelrahman.com/otp-system/status.php"

# --- App Initialization ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- Helper Functions ---

def create_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(subject: str):
    return create_token({"sub": subject}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

def create_refresh_token(subject: str):
    return create_token({"sub": subject}, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)

def hash_password(password):
    return bcrypt.hash(password)

def generate_student_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def decode_token_or_none(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# **CORRECTED DEPENDENCY**
# Dependency to get current student from DB. The old get_db parameter is now removed.
async def get_current_student(token: str = Depends(oauth2_scheme)):
    payload = decode_token_or_none(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    student = await student_collection.find_one({"_id": ObjectId(sub)})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student

# --- API Endpoints ---

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/register")
async def register(data: RegisterRequest):
    # Check if phone or email already exists
    if await student_collection.find_one({"$or": [{"phone": data.phone}, {"email": data.email}]}):
        raise HTTPException(status_code=400, detail="Phone or Email already exists")

    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    hashed_pass = hash_password(data.password)
    new_student_code = generate_student_code()

    student_data = data.dict()
    student_data.pop("confirm_password")
    student_data["password"] = hashed_pass
    student_data["student_code"] = new_student_code

    result = await student_collection.insert_one(student_data)
    new_student_id = str(result.inserted_id)

    # Send OTP (optional, can be commented out for testing)
    try:
        requests.post(OTP_SEND_URL, data={"email": data.email})
    except Exception as e:
        print("Failed to send OTP:", e)

    return {
        "message": "Registered successfully. Please verify your email.",
        "access_token": create_access_token(new_student_id),
        "refresh_token": create_refresh_token(new_student_id),
        "student": {
            "id": new_student_id,
            "student_code": new_student_code,
            "name": data.name,
            "phone": data.phone,
            "email": data.email,
        }
    }

@app.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    student = await student_collection.find_one({
        "$or": [
            {"phone": data.identifier},
            {"email": data.identifier},
            {"student_code": data.identifier}
        ]
    })

    if not student or not verify_password(data.password, student["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # The OTP check logic (if you wish to implement it fully) would go here.
    # For now, a successful password check is enough to log in.

    student_id = str(student["_id"])
    return {
        "access_token": create_access_token(student_id),
        "refresh_token": create_refresh_token(student_id)
    }

@app.get("/student/profile", response_model=StudentProfileResponse)
async def get_student_profile(current_student: dict = Depends(get_current_student)):
    # The dependency returns the student document from MongoDB
    # We add the id field to the response, converting the ObjectId
    profile_data = current_student.copy()
    profile_data['id'] = str(current_student['_id'])
    return StudentProfileResponse(**profile_data)


@app.put("/student/profile/edit")
async def edit_profile(data: StudentEditRequest, current_student: dict = Depends(get_current_student)):
    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided to update")
    
    # Hash password if it's being updated
    if "password" in update_data and update_data["password"]:
        update_data["password"] = hash_password(update_data["password"])
    else:
        update_data.pop("password", None) # Remove password from update if it's empty

    await student_collection.update_one(
        {"_id": current_student["_id"]},
        {"$set": update_data}
    )

    # Fetch the updated student data to return
    updated_student_doc = await student_collection.find_one({"_id": current_student["_id"]})
    
    # Prepare the response using the Pydantic model to ensure structure
    response_data = StudentProfileResponse(**updated_student_doc).dict()
    # Manually exclude the hashed password from the final JSON response
    response_data.pop("password", None)


    return {
        "message": "Profile updated successfully",
        "student": response_data
    }

class RefreshRequest(BaseModel):
    refresh_token: str

@app.post("/token/refresh")
async def refresh_token(data: RefreshRequest):
    payload = decode_token_or_none(data.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    # Check if student still exists in the database
    student = await student_collection.find_one({"_id": ObjectId(sub)})
    if not student:
        raise HTTPException(status_code=401, detail="User for this token no longer exists")

    new_access = create_access_token(sub)
    new_refresh = create_refresh_token(sub)

    return {"access_token": new_access, "refresh_token": new_refresh}
