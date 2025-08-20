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
        await db.client.admin.command('ping')
        print("MongoDB connection successful.")
    except Exception as e:
        print("------------------------------------------------------")
        print("FATAL ERROR: Could not connect to MongoDB.")
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

async def get_token_blacklist_collection():
    database = await get_database()
    collection = database.get_collection("token_blacklist")
    index_name = "expire_at_1"
    if index_name not in await collection.index_information():
        await collection.create_index("expire_at", expireAfterSeconds=0)
    return collection

async def get_receipt_collection():
    database = await get_database()
    return database.get_collection("receipts")

# NEW: Collection for password reset codes
async def get_password_reset_collection():
    database = await get_database()
    collection = database.get_collection("password_reset_codes")
    # This TTL index automatically deletes codes after 10 minutes
    index_name = "expire_at_1"
    if index_name not in await collection.index_information():
        await collection.create_index("expire_at", expireAfterSeconds=0)
    return collection

async def get_favorite_videos_collection():
    database = await get_database()
    return database.get_collection("favorite_videos")

# NEW: Functions to get collections for mock data
async def get_educational_content_collection():
    database = await get_database()
    return database.get_collection("educational_content")

async def get_books_collection():
    database = await get_database()
    return database.get_collection("books")

async def get_mock_test_results_collection():
    database = await get_database()
    return database.get_collection("mock_test_results")

async def get_mock_videos_collection():
    database = await get_database()
    return database.get_collection("mock_videos")