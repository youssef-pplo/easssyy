# database.py
import os
import motor.motor_asyncio
# database.py
from dotenv import load_dotenv

load_dotenv() # This line reads your .env file

MONGO_URI = os.environ.get("MONGODB_URI")

# Create an async client to connect to your MongoDB Atlas cluster
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)

# Get a reference to your database (it will be created if it doesn't exist)
db = client.easybio_db

# Get a reference to your collection of students (like a table in SQL)
student_collection = db.get_collection("students")
