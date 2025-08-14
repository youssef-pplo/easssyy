# database.py
import os
import motor.motor_asyncio
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ.get("MONGODB_URI")

class DataBase:
    client: motor.motor_asyncio.AsyncIOMotorClient = None

db = DataBase()

async def get_database() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    return db.client.easybio_db

async def connect_to_mongo():
    print("Connecting to MongoDB...")
    db.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    print("Connection successful.")

async def close_mongo_connection():
    print("Closing MongoDB connection...")
    db.client.close()
    print("Connection closed.")

# We get the collection from the database now
async def get_student_collection():
    database = await get_database()
    return database.get_collection("students")
