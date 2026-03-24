"""
CRUD operations for the Lead Management System.
Integrated with MongoDB for persistence and scalability.
"""
import json
import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models import User, RoleEnum, LeadStatus
from schemas import LeadCreate, LeadUpdate, UserCreate, FollowUpCreate, PaymentProofCreate
from auth import get_password_hash
import mongodb

# ========== USER OPERATIONS (SQL) ==========

def get_user_by_username(db: Session, username: str):
    """Retrieve a user by their username."""
    return db.query(User).filter(User.username == username).first()

def create_user(db: Session, user: UserCreate):
    """Create a new user with hashed password."""
    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, password_hash=hashed_password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# ========== LEAD OPERATIONS (MongoDB) ==========

async def log_activity(lead_id: int, user_id: int, action: str,
                       prev_state: str = None, new_state: str = None, details: str = None):
    """Log an activity event for a specific lead in MongoDB."""
    mongo_db = mongodb.get_mongo_db()
    if mongo_db is None:
        return
    
    activity = {
        "lead_id": lead_id,
        "user_id": user_id,
        "action": action,
        "previous_state": prev_state,
        "new_state": new_state,
        "details": details,
        "timestamp": datetime.datetime.utcnow()
    }
    await mongo_db.activities.insert_one(activity)

async def auto_assign_lead(db: Session):
    """Auto-assign logic remains SQL-based for user lookup."""
    telecaller = db.query(User).filter(User.role == RoleEnum.TELECALLER).first()
    if telecaller:
        return telecaller.id
    counsellor = db.query(User).filter(User.role == RoleEnum.COUNSELLOR).first()
    return counsellor.id if counsellor else None

async def create_lead(db: Session, lead: LeadCreate, current_user: User):
    """Create a new lead in MongoDB."""
    mongo_db = mongodb.get_mongo_db()
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="Database connection not available")

    assigned_to_id = await auto_assign_lead(db)
    lead_id = await mongodb.get_next_sequence_value("leads")
    
    now = datetime.datetime.utcnow()
    new_lead_doc = {
        "id": lead_id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "source": lead.source,
        "status": LeadStatus.NEW.value,
        "assigned_to_id": assigned_to_id,
        "created_by_id": current_user.id,
        "created_at": now,
        "updated_at": now,
        "version": 1
    }
    
    await mongo_db.leads.insert_one(new_lead_doc)
    await log_activity(
        lead_id, current_user.id, "CREATE",
        new_state=LeadStatus.NEW.value, details="Lead created"
    )
    
    return new_lead_doc

async def get_leads(db: Session, current_user: User):
    """Retrieve leads from MongoDB based on user role."""
    mongo_db = mongodb.get_mongo_db()
    if mongo_db is None:
        return []

    query = {}
    if current_user.role != RoleEnum.ADMIN:
        query = {
            "$or": [
                {"assigned_to_id": current_user.id},
                {"created_by_id": current_user.id}
            ]
        }
    
    cursor = mongo_db.leads.find(query).sort("created_at", -1)
    leads = await cursor.to_list(length=1000)
    # Ensure ID is included in the output for Pydantic
    for l in leads:
        l.pop("_id", None)
    return leads

async def update_lead(db: Session, lead_id: int, lead_update: LeadUpdate, current_user: User):
    """Update a lead in MongoDB."""
    mongo_db = mongodb.get_mongo_db()
    if mongo_db is None:
        raise HTTPException(503, "DB error")

    lead = await mongo_db.leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if current_user.role != RoleEnum.ADMIN and lead["assigned_to_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if lead["version"] != lead_update.version:
        raise HTTPException(status_code=409, detail="Concurrent update")

    update_doc = {"$set": {"updated_at": datetime.datetime.utcnow()}, "$inc": {"version": 1}}
    prev_state = lead["status"]
    notes_added = ""

    if lead_update.status and lead_update.status.value != lead["status"]:
        if lead["status"] in [LeadStatus.CONVERTED.value, LeadStatus.DEAD.value]:
            raise HTTPException(status_code=400, detail="Terminal lead")

        if lead_update.status == LeadStatus.ESCALATED:
            if not lead_update.reason:
                raise HTTPException(400, "Reason required")
            notes_added += f"Escalated: {lead_update.reason} "
            counsellor = db.query(User).filter(User.role == RoleEnum.COUNSELLOR).first()
            if counsellor and current_user.role == RoleEnum.TELECALLER:
                update_doc["$set"]["assigned_to_id"] = counsellor.id
        
        update_doc["$set"]["status"] = lead_update.status.value
        await log_activity(lead_id, current_user.id, "STATUS_CHANGE", 
                         prev_state=prev_state, new_state=lead_update.status.value, details=notes_added)

    if lead_update.assigned_to_id and current_user.role in [RoleEnum.ADMIN, RoleEnum.COUNSELLOR]:
        if not lead_update.reason:
            raise HTTPException(400, "Reason required for reassignment")
        update_doc["$set"]["assigned_to_id"] = lead_update.assigned_to_id
        await log_activity(lead_id, current_user.id, "REASSIGNED", 
                         details=f"To {lead_update.assigned_to_id}. Reason: {lead_update.reason}")

    if lead_update.notes:
        await log_activity(lead_id, current_user.id, "NOTE", details=lead_update.notes)

    await mongo_db.leads.update_one({"id": lead_id}, update_doc)
    res = await mongo_db.leads.find_one({"id": lead_id})
    if "_id" in res: del res["_id"]
    return res

# ========== FOLLOWUPS & PAYMENTS (MongoDB) ==========

async def create_followup(lead_id: int, followup: FollowUpCreate, current_user: User):
    """Schedule a follow-up in MongoDB."""
    mongo_db = mongodb.get_mongo_db()
    lead = await mongo_db.leads.find_one({"id": lead_id})
    if not lead or (lead["assigned_to_id"] != current_user.id and current_user.role != RoleEnum.ADMIN):
        raise HTTPException(403, "Unauthorized")

    followup_doc = {
        "lead_id": lead_id,
        "user_id": current_user.id,
        "scheduled_date": followup.scheduled_date,
        "notes": followup.notes,
        "status": "Pending",
        "created_at": datetime.datetime.utcnow()
    }
    await mongo_db.followups.insert_one(followup_doc)
    await log_activity(lead_id, current_user.id, "FOLLOWUP_SCHEDULED", 
                      details=f"For {followup.scheduled_date}")
    return {"message": "Followup scheduled"}

async def create_payment_proof(lead_id: int, proof: PaymentProofCreate, current_user: User):
    """Upload payment proof in MongoDB."""
    mongo_db = mongodb.get_mongo_db()
    lead = await mongo_db.leads.find_one({"id": lead_id})
    if not lead: raise HTTPException(404, "Lead not found")

    # Versioning check in Mongo
    last_proof = await mongo_db.payments.find_one({"lead_id": lead_id}, sort=[("version", -1)])
    new_version = 1 if not last_proof else last_proof["version"] + 1

    proof_doc = {
        "lead_id": lead_id,
        "file_url": proof.file_url,
        "version": new_version,
        "status": "Pending",
        "created_by_id": current_user.id,
        "created_at": datetime.datetime.utcnow()
    }
    await mongo_db.payments.insert_one(proof_doc)
    await log_activity(lead_id, current_user.id, "PAYMENT_UPLOAD", details=f"Version {new_version}")
    return {"message": "Payment proof uploaded", "version": new_version}

async def convert_lead(db: Session, lead_id: int, current_user: User):
    """Convert a lead to a student in MongoDB."""
    if current_user.role == RoleEnum.TELECALLER:
        raise HTTPException(status_code=403, detail="Forbidden")

    mongo_db = mongodb.get_mongo_db()
    lead = await mongo_db.leads.find_one({"id": lead_id})
    if not lead or lead["status"] == LeadStatus.CONVERTED.value:
        raise HTTPException(400, "Invalid lead")

    # Create student record
    student_doc = {
        "lead_id": lead_id,
        "name": lead["name"],
        "email": lead["email"],
        "phone": lead["phone"],
        "enrolled_at": datetime.datetime.utcnow()
    }
    await mongo_db.students.insert_one(student_doc)
    await mongo_db.leads.update_one({"id": lead_id}, {"$set": {"status": LeadStatus.CONVERTED.value}})
    await log_activity(lead_id, current_user.id, "CONVERTED", details="Converted to student")
    
    res = await mongo_db.leads.find_one({"id": lead_id})
    if "_id" in res: del res["_id"]
    return res
