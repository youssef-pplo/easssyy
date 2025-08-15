
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
    # This check ensures the client is connected before trying to get the DB
    if db.client is None:
        await connect_to_mongo()
    return db.client.easybio_db

async def connect_to_mongo():
    print("Attempting to connect to MongoDB...")
    if not MONGO_URI:
        print("FATAL ERROR: MONGODB_URI environment variable is not set on Vercel.")
        # In a serverless environment, we shouldn't exit, but this indicates a critical config error.
        return

    try:
        # Create a new client instance for the serverless function
        db.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        await db.client.admin.command('ping')
        print("MongoDB connection successful.")
    except Exception as e:
        print("------------------------------------------------------")
        print("FATAL ERROR: Could not connect to MongoDB.")
        print(f"Error details: {e}")
        print("------------------------------------------------------")

async def close_mongo_connection():
    if db.client:
        print("Closing MongoDB connection...")
        db.client.close()
        db.client = None # Important for serverless environments
        print("Connection closed.")

async def get_student_collection():
    database = await get_database()
    return database.get_collection("students")

async def get_token_blacklist_collection():
    database = await get_database()
    collection = database.get_collection("token_blacklist")
    # This TTL index automatically deletes tokens from the blacklist after they expire
    index_name = "expire_at_1"
    existing_indexes = await collection.index_information()
    if index_name not in existing_indexes:
        await collection.create_index("expire_at", expireAfterSeconds=0)
    return collection

async def get_receipt_collection():
    database = await get_database()
    return database.get_collection("receipts")

async def get_password_reset_collection():
    database = await get_database()
    collection = database.get_collection("password_reset_codes")
    # This TTL index automatically deletes codes after 10 minutes
    index_name = "expire_at_1"
    existing_indexes = await collection.index_information()
    if index_name not in existing_indexes:
        await collection.create_index("expire_at", expireAfterSeconds=0)
    return collection
