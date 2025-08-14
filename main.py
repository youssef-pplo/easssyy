# main.py
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import HTMLResponse # <-- NEW IMPORT
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

# Dependency to get current student from DB
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

    student_id = str(student["_id"])
    return {
        "access_token": create_access_token(student_id),
        "refresh_token": create_refresh_token(student_id)
    }

@app.get("/student/profile", response_model=StudentProfileResponse)
async def get_student_profile(current_student: dict = Depends(get_current_student)):
    profile_data = current_student.copy()
    profile_data['id'] = str(current_student['_id'])
    return StudentProfileResponse(**profile_data)


@app.put("/student/profile/edit")
async def edit_profile(data: StudentEditRequest, current_student: dict = Depends(get_current_student)):
    update_data = data.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided to update")
    
    if "password" in update_data and update_data["password"]:
        update_data["password"] = hash_password(update_data["password"])
    else:
        update_data.pop("password", None)

    await student_collection.update_one(
        {"_id": current_student["_id"]},
        {"$set": update_data}
    )

    updated_student_doc = await student_collection.find_one({"_id": current_student["_id"]})
    
    response_data = StudentProfileResponse(**updated_student_doc).dict()
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

    student = await student_collection.find_one({"_id": ObjectId(sub)})
    if not student:
        raise HTTPException(status_code=401, detail="User for this token no longer exists")

    new_access = create_access_token(sub)
    new_refresh = create_refresh_token(sub)

    return {"access_token": new_access, "refresh_token": new_refresh}


# --- NEW TESTING FRONTEND ---
@app.get("/try", response_class=HTMLResponse)
async def get_test_frontend():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>API Tester</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; background-color: #f4f4f9; color: #333; }
            .container { max-width: 800px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1, h2 { color: #5a5a5a; border-bottom: 2px solid #eee; padding-bottom: 10px; }
            form { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
            input, button { padding: 10px; border-radius: 5px; border: 1px solid #ddd; font-size: 16px; }
            button { background-color: #007bff; color: white; border: none; cursor: pointer; transition: background-color 0.2s; }
            button:hover { background-color: #0056b3; }
            pre { background-color: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; }
            .token-storage { margin-top: 20px; }
            .token-storage input { width: 100%; box-sizing: border-box; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>API Tester</h1>

            <div class="token-storage">
                <h2>Token Storage</h2>
                <label for="accessToken">Access Token:</label>
                <input type="text" id="accessToken" placeholder="Access token will appear here after login/register">
                <label for="refreshToken">Refresh Token:</label>
                <input type="text" id="refreshToken" placeholder="Refresh token will appear here after login/register">
            </div>

            <h2>/register</h2>
            <form id="registerForm">
                <input type="text" id="regName" placeholder="Name" value="Test User">
                <input type="text" id="regPhone" placeholder="Phone" value="1234567890">
                <input type="email" id="regEmail" placeholder="Email" value="test@example.com">
                <input type="text" id="regParentPhone" placeholder="Parent Phone" value="0987654321">
                <input type="text" id="regCity" placeholder="City" value="Cairo">
                <input type="text" id="regGrade" placeholder="Grade" value="10">
                <input type="text" id="regLang" placeholder="Language" value="en">
                <input type="password" id="regPassword" placeholder="Password" value="password123">
                <input type="password" id="regConfirmPassword" placeholder="Confirm Password" value="password123">
                <button type="submit">Register</button>
            </form>

            <h2>/login</h2>
            <form id="loginForm">
                <input type="text" id="loginIdentifier" placeholder="Email, Phone, or Student Code" value="test@example.com">
                <input type="password" id="loginPassword" placeholder="Password" value="password123">
                <button type="submit">Login</button>
            </form>

            <h2>/student/profile (GET)</h2>
            <button id="getProfileBtn">Get Profile</button>

            <h2>/student/profile/edit (PUT)</h2>
            <form id="editProfileForm">
                <input type="text" id="editName" placeholder="New Name">
                <input type="email" id="editEmail" placeholder="New Email">
                <button type="submit">Update Profile</button>
            </form>

            <h2>/token/refresh (POST)</h2>
            <button id="refreshTokenBtn">Refresh Token</button>

            <h2>API Response</h2>
            <pre id="responseOutput">Response will be shown here...</pre>
        </div>

        <script>
            const responseOutput = document.getElementById('responseOutput');
            const accessTokenInput = document.getElementById('accessToken');
            const refreshTokenInput = document.getElementById('refreshToken');

            async function apiCall(endpoint, method = 'GET', body = null, token = null) {
                const headers = { 'Content-Type': 'application/json' };
                if (token) {
                    headers['Authorization'] = `Bearer ${token}`;
                }

                try {
                    const options = { method, headers };
                    if (body) {
                        options.body = JSON.stringify(body);
                    }
                    const response = await fetch(endpoint, options);
                    const data = await response.json();
                    responseOutput.textContent = JSON.stringify(data, null, 2);
                    
                    if (data.access_token) {
                        accessTokenInput.value = data.access_token;
                    }
                    if (data.refresh_token) {
                        refreshTokenInput.value = data.refresh_token;
                    }
                } catch (error) {
                    responseOutput.textContent = `Error: ${error.message}`;
                }
            }

            // Register
            document.getElementById('registerForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const body = {
                    name: document.getElementById('regName').value,
                    phone: document.getElementById('regPhone').value,
                    email: document.getElementById('regEmail').value,
                    parent_phone: document.getElementById('regParentPhone').value,
                    city: document.getElementById('regCity').value,
                    grade: document.getElementById('regGrade').value,
                    lang: document.getElementById('regLang').value,
                    password: document.getElementById('regPassword').value,
                    confirm_password: document.getElementById('regConfirmPassword').value,
                };
                apiCall('/register', 'POST', body);
            });

            // Login
            document.getElementById('loginForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const body = {
                    identifier: document.getElementById('loginIdentifier').value,
                    password: document.getElementById('loginPassword').value,
                };
                apiCall('/login', 'POST', body);
            });

            // Get Profile
            document.getElementById('getProfileBtn').addEventListener('click', () => {
                const token = accessTokenInput.value;
                if (!token) {
                    responseOutput.textContent = 'Error: Access token is missing. Please log in first.';
                    return;
                }
                apiCall('/student/profile', 'GET', null, token);
            });

            // Edit Profile
            document.getElementById('editProfileForm').addEventListener('submit', (e) => {
                e.preventDefault();
                const token = accessTokenInput.value;
                 if (!token) {
                    responseOutput.textContent = 'Error: Access token is missing. Please log in first.';
                    return;
                }
                const body = {};
                const name = document.getElementById('editName').value;
                const email = document.getElementById('editEmail').value;
                if(name) body.name = name;
                if(email) body.email = email;
                
                apiCall('/student/profile/edit', 'PUT', body, token);
            });
            
            // Refresh Token
            document.getElementById('refreshTokenBtn').addEventListener('click', () => {
                const token = refreshTokenInput.value;
                if (!token) {
                    responseOutput.textContent = 'Error: Refresh token is missing. Please log in or register first.';
                    return;
                }
                apiCall('/token/refresh', 'POST', { refresh_token: token });
            });

        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
