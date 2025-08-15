# database.py
import os
import motor.motor_asyncio
from dotenv import load_dotenv
import sys

load_dotenv()

MONGO_URI = os.environ.get("MONGODB_URI")

# We will manage the client connection on a per-request basis
# This is the most reliable pattern for serverless environments like Vercel

async def get_db_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    """
    Dependency function that creates and yields a new MongoDB client for each request.
    This ensures that each serverless invocation gets a fresh, valid connection.
    """
    if not MONGO_URI:
        print("FATAL ERROR: MONGODB_URI environment variable is not set.")
        # In a serverless function, we should raise an exception to signal a configuration error
        raise HTTPException(status_code=500, detail="Database configuration error.")

    client = None
    try:
        print("Creating new MongoDB client for request...")
        client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        await client.admin.command('ping') # Verify connection
        yield client
    finally:
        if client:
            print("Closing MongoDB client for request.")
            client.close()

async def get_database(client: motor.motor_asyncio.AsyncIOMotorClient = Depends(get_db_client)):
    return client.easybio_db

async def get_student_collection(db = Depends(get_database)):
    return db.get_collection("students")

async def get_token_blacklist_collection(db = Depends(get_database)):
    collection = db.get_collection("token_blacklist")
    index_name = "expire_at_1"
    # This check is now less critical per-request but good practice
    # In a real high-traffic app, you might run index creation separately
    try:
        existing_indexes = await collection.index_information()
        if index_name not in existing_indexes:
            await collection.create_index("expire_at", expireAfterSeconds=0)
    except Exception as e:
        print(f"Could not ensure index on token_blacklist: {e}")
    return collection

async def get_receipt_collection(db = Depends(get_database)):
    return db.get_collection("receipts")

async def get_password_reset_collection(db = Depends(get_database)):
    collection = db.get_collection("password_reset_codes")
    try:
        existing_indexes = await collection.index_information()
        index_name = "expire_at_1"
        if index_name not in existing_indexes:
            await collection.create_index("expire_at", expireAfterSeconds=0)
    except Exception as e:
        print(f"Could not ensure index on password_reset_codes: {e}")
    return collection
