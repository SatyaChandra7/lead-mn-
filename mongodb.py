"""
MongoDB configuration and connection management using Motor.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import Field
from typing import Optional

# MongoDB Connection String (fallback to localhost)
MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "lead_crm")

# Global variables for the database client and database
client: Optional[AsyncIOMotorClient] = None
db = None

async def connect_to_mongo():
    global client, db
    print(f"Connecting to MongoDB at {MONGODB_URL}...")
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        # Ping the database to verify connection
        await client.admin.command('ping')
        print("Connected to MongoDB successfully!")
    except Exception as e:
        print(f"Could not connect to MongoDB: {e}")
        raise e

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")

def get_mongo_db():
    if db is None:
        # In case it's called before connect_to_mongo (though unlikely in FastAPI)
        return None
    return db

async def get_next_sequence_value(sequence_name: str):
    """Generate an auto-incrementing integer ID for MongoDB collections."""
    result = await db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"sequence_value": 1}},
        upsert=True,
        return_document=True
    )
    return result["sequence_value"]
