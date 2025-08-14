# database.py
import os
import motor.motor_asyncio
from dotenv import load_dotenv
import sys

load_dotenv()

MONGO_URI = os.environ.get("MONGODB_URI")

class DataBase:
    client: motor.motor_asyncio.AsyncIOMotorClient = None

db = DataBase()

async def get_database() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    return db.client.easybio_db

async def connect_to_mongo():
    print("Attempting to connect to MongoDB...")
    if not MONGO_URI:
        print("FATAL ERROR: MONGODB_URI environment variable is not set.")
        sys.exit(1)
    
    try:
        db.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        # Validate the connection by sending a ping
        await db.client.admin.command('ping')
        print("MongoDB connection successful.")
    except Exception as e:
        print("------------------------------------------------------")
        print("FATAL ERROR: Could not connect to MongoDB.")
        print("Please check your MONGODB_URI, password (no special characters), and IP access rules.")
        print(f"Error details: {e}")
        print("------------------------------------------------------")
        sys.exit(1)

async def close_mongo_connection():
    if db.client:
        print("Closing MongoDB connection...")
        db.client.close()
        print("Connection closed.")

async def get_student_collection():
    database = await get_database()
    return database.get_collection("students")
