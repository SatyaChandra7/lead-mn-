"""
Main application module for the Lead Management CRM.
Integrated with MongoDB for persistent lead storage and history.
"""
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

import auth
import crud
import models
import schemas
from database import engine, Base, get_db, SessionLocal
import mongodb

def seed_data():
    """Auto-seed demo users if not exists (SQL)."""
    db = SessionLocal()
    try:
        # Seed Admin
        if not crud.get_user_by_username(db, "admin"):
            crud.create_user(db, schemas.UserCreate(username="admin", password="password123", role=models.RoleEnum.ADMIN))
        
        # Seed Counsellor
        if not crud.get_user_by_username(db, "counsellor1"):
            crud.create_user(db, schemas.UserCreate(username="counsellor1", password="password123", role=models.RoleEnum.COUNSELLOR))

        # Seed Telecaller
        if not crud.get_user_by_username(db, "telecaller1"):
            crud.create_user(db, schemas.UserCreate(username="telecaller1", password="password123", role=models.RoleEnum.TELECALLER))
    except SQLAlchemyError as err:
        print(f"Error seeding users: {err}")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    try:
        # SQL Initialization (Users)
        Base.metadata.create_all(bind=engine)
        seed_data()
        
        # MongoDB Initialization (Leads)
        await mongodb.connect_to_mongo()
        
    except Exception as err:
        print(f"Initialization error: {err}")
    
    yield
    await mongodb.close_mongo_connection()

app = FastAPI(title="Lead Management CRM", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== AUTHENTICATION ==========

@app.post("/token", response_model=schemas.Token, tags=["Auth"])
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                           db: Session = Depends(get_db)):
    """Generate an access token for a user."""
    user = crud.get_user_by_username(db, form_data.username)
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    
    access_token = auth.create_access_token(
        data={"sub": user.username, "role": user.role.value},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

# ========== USERS ==========

@app.post("/users/register", response_model=schemas.UserOut, tags=["Users"])
def register_user(user: schemas.UserCreate,
                  db: Session = Depends(get_db),
                  _current_user: models.User = Depends(auth.require_role(["Admin"]))):
    """Register a new user (Restricted to Admin)."""
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

@app.get("/users/me", response_model=schemas.UserOut, tags=["Users"])
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    """Get the profile of the current authenticated user."""
    return current_user

@app.get("/admin/stats", tags=["Admin"])
async def get_admin_stats(_admin: models.User = Depends(auth.require_role(["Admin"]))):
    """Retrieve dashboard metrics from MongoDB (Admin Only)."""
    mongo_db = mongodb.get_mongo_db()
    if mongo_db is None:
        return {"total_leads": 0, "converted": 0, "follow_up_needed": 0, "conversion_rate": "0%"}

    total_leads = await mongo_db.leads.count_documents({})
    converted = await mongo_db.leads.count_documents({"status": models.LeadStatus.CONVERTED.value})
    follow_ups = await mongo_db.leads.count_documents({"status": models.LeadStatus.FOLLOW_UP.value})
    
    rate = f"{(converted/total_leads*100):.1f}%" if total_leads > 0 else "0%"
    return {
        "total_leads": total_leads,
        "converted": converted,
        "follow_up_needed": follow_ups,
        "conversion_rate": rate
    }

# ========== LEADS ==========

@app.post("/leads", response_model=schemas.LeadOut, tags=["Leads"])
async def create_lead(lead: schemas.LeadCreate,
                db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.require_role(["Admin", "Counsellor", "Telecaller"]))):
    """Create a new lead (Saved to MongoDB for persistence)."""
    return await crud.create_lead(db=db, lead=lead, current_user=current_user)

@app.get("/leads", response_model=List[schemas.LeadOut], tags=["Leads"])
async def read_leads(db: Session = Depends(get_db),
               current_user: models.User = Depends(auth.get_current_user)):
    """List all leads accessible to the current user (From MongoDB)."""
    return await crud.get_leads(db=db, current_user=current_user)

@app.put("/leads/{lead_id}", response_model=schemas.LeadOut, tags=["Leads"])
async def update_lead(lead_id: int,
                lead_update: schemas.LeadUpdate,
                db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)):
    """Update lead details or status (MongoDB)."""
    return await crud.update_lead(db, lead_id, lead_update, current_user)

@app.post("/leads/{lead_id}/convert", response_model=schemas.LeadOut, tags=["Leads"])
async def convert_lead_to_student(lead_id: int,
                            db: Session = Depends(get_db),
                            current_user: models.User = Depends(
                                auth.require_role(["Admin", "Counsellor"])
                            )):
    """Convert a lead to a student (MongoDB)."""
    return await crud.convert_lead(db, lead_id, current_user)

# ========== FOLLOW-UPS & PAYMENTS (MongoDB Integrated) ==========

@app.post("/leads/{lead_id}/followups", tags=["FollowUps"])
async def create_followup(lead_id: int,
                    followup: schemas.FollowUpCreate,
                    current_user: models.User = Depends(auth.get_current_user)):
    """Schedule a followup for a lead using MongoDB."""
    return await crud.create_followup(lead_id, followup, current_user)

@app.post("/leads/{lead_id}/payments", tags=["Payments"])
async def upload_payment_proof(lead_id: int,
                         proof: schemas.PaymentProofCreate,
                         current_user: models.User = Depends(auth.get_current_user)):
    """Upload payment proof (MongoDB)."""
    return await crud.create_payment_proof(lead_id, proof, current_user)

# ========== FRONTEND ==========

frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
