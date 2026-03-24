
import asyncio
import sqlite3
import datetime
import os
from motor.motor_asyncio import AsyncIOMotorClient

# Configuration
SQLITE_DB = "leads.db"
MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "lead_crm")

async def migrate_sqlite_to_mongodb():
    """Migrate all Lead data from SQLite to MongoDB to ensure persistent storage."""
    if not os.path.exists(SQLITE_DB):
        print("leads.db not found locally. No data to migrate.")
        return

    print(f"Connecting to MongoDB at {MONGODB_URL}...")
    try:
        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
        await client.admin.command('ping')
        mongo_db = client[DATABASE_NAME]
        
        conn = sqlite3.connect(SQLITE_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Migrate Leads
        cursor.execute("SELECT * FROM leads")
        leads_sql = cursor.fetchall()
        max_id = 0
        for lead in leads_sql:
            ld = dict(lead)
            if ld.get("created_at"): ld["created_at"] = datetime.datetime.fromisoformat(ld["created_at"].split('+')[0])
            if ld.get("updated_at"): ld["updated_at"] = datetime.datetime.fromisoformat(ld["updated_at"].split('+')[0])
            await mongo_db.leads.update_one({"id": ld["id"]}, {"$set": ld}, upsert=True)
            if ld["id"] > max_id: max_id = ld["id"]
        
        # Sync Counter
        await mongo_db.counters.update_one({"_id": "leads"}, {"$set": {"sequence_value": max_id}}, upsert=True)
        print(f"Leads migrated: {len(leads_sql)}")

        # 2. Migrate Activities
        cursor.execute("SELECT * FROM lead_activities")
        activities = cursor.fetchall()
        for act in activities:
            ad = dict(act)
            if ad.get("timestamp"): ad["timestamp"] = datetime.datetime.fromisoformat(ad["timestamp"].split('+')[0])
            await mongo_db.activities.insert_one(ad)
        print(f"Activities migrated: {len(activities)}")

        print("\nAll data successfully saved to MongoDB.")
        client.close()
    except Exception as e:
        print(f"Error during migration: {e}")
        print("Tip: Make sure MongoDB is running or your MONGODB_URL is correct.")

if __name__ == "__main__":
    asyncio.run(migrate_sqlite_to_mongodb())
