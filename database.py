# database.py
import os
import motor.motor_asyncio
from dotenv import load_dotenv

load_dotenv()

# Get the MongoDB connection string from environment variables
MONGO_URI = "mongodb+srv://youssefdev74:h3P0rZS2ZDU0zoYA@cluster0.1msxyqh.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Create an async client to connect to your MongoDB Atlas cluster
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)

# Get a reference to your database (it will be created if it doesn't exist)
db = client.easybio_db

# Get a reference to your collection of students (like a table in SQL)
student_collection = db.get_collection("students")
