from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import engine, Base, get_db, SessionLocal
import models, schemas, crud, auth

# Auto-seed admin user if not exists
def seed_admin():
    db = SessionLocal()
    try:
        admin_user = crud.get_user_by_username(db, "admin")
        if not admin_user:
            crud.create_user(
                db, schemas.UserCreate(
                    username="admin", 
                    password="password123", 
                    role=models.RoleEnum.Admin
                )
            )
            print("Admin user created: admin / password123")
    except Exception as e:
        print(f"Error seeding admin user: {e}")
    finally:
        db.close()

from contextlib import asynccontextmanager

# Define lifespan to handle startup tasks
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create Database tables
    try:
        Base.metadata.create_all(bind=engine)
        seed_admin()
    except Exception as e:
        print(f"Database initialization error: {e}")
    yield

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
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_username(db, form_data.username)
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username, "role": user.role.value}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# ========== USERS ==========

@app.post("/users/register", response_model=schemas.UserOut, tags=["Users"])
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["Admin"]))):
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

@app.get("/users/me", response_model=schemas.UserOut, tags=["Users"])
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# ========== LEADS ==========

@app.post("/leads", response_model=schemas.LeadOut, tags=["Leads"])
def create_lead(lead: schemas.LeadCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["Admin", "Counsellor"]))):
    return crud.create_lead(db=db, lead=lead, current_user=current_user)

@app.get("/leads", tags=["Leads"])
def read_leads(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return crud.get_leads(db=db, current_user=current_user)

@app.put("/leads/{lead_id}", tags=["Leads"])
def update_lead(lead_id: int, lead_update: schemas.LeadUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return crud.update_lead(db, lead_id, lead_update, current_user)

@app.post("/leads/{lead_id}/convert", tags=["Leads"])
def convert_lead_to_student(lead_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["Admin", "Counsellor"]))):
    return crud.convert_lead(db, lead_id, current_user)

# ========== FOLLOW-UPS ==========

@app.post("/leads/{lead_id}/followups", tags=["FollowUps"])
def create_followup(lead_id: int, followup: schemas.FollowUpCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead or lead.assigned_to_id != current_user.id and current_user.role != models.RoleEnum.Admin:
        raise HTTPException(403, "Not authorized to add followup")
    
    new_followup = models.FollowUp(
        lead_id=lead_id,
        user_id=current_user.id,
        scheduled_date=followup.scheduled_date,
        notes=followup.notes
    )
    db.add(new_followup)
    
    crud.log_activity(db, lead_id, current_user.id, "FOLLOWUP_SCHEDULED", details=f"Followup scheduled for {followup.scheduled_date}")
    db.commit()
    return {"message": "Followup scheduled"}

# ========== PAYMENTS (Versioning & Validation) ==========

@app.post("/leads/{lead_id}/payments", tags=["Payments"])
def upload_payment_proof(lead_id: int, proof: schemas.PaymentProofCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    
    # Check if existing pending proof
    existing = db.query(models.PaymentProof).filter(models.PaymentProof.lead_id == lead_id).order_by(models.PaymentProof.version.desc()).first()
    new_version = 1 if not existing else existing.version + 1

    new_proof = models.PaymentProof(
        lead_id=lead_id,
        file_url=proof.file_url,
        version=new_version
    )
    db.add(new_proof)
    crud.log_activity(db, lead_id, current_user.id, "PAYMENT_UPLOAD", details=f"Version {new_version} uploaded")
    db.commit()
    return {"message": "Payment proof uploaded", "version": new_version}

@app.put("/leads/{lead_id}/payments/{version}/verify", tags=["Payments"])
def verify_payment_proof(lead_id: int, version: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.require_role(["Admin", "Counsellor"]))):
    proof = db.query(models.PaymentProof).filter(
        models.PaymentProof.lead_id == lead_id, models.PaymentProof.version == version
    ).first()
    if not proof:
        raise HTTPException(404, "Payment proof not found")
    
    proof.status = "Verified"
    proof.verified_by_id = current_user.id
    
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    crud.log_activity(db, lead_id, current_user.id, "PAYMENT_VERIFIED", details=f"Verified version {version}")
    
    db.commit()
    return {"message": "Payment proof verified"}

# ========== FRONTEND ==========
from pathlib import Path

# Static files should be served from the frontend folder
frontend_dir = Path(__file__).parent / "frontend"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    print(f"Warning: Frontend directory '{frontend_dir}' not found. UI will not be served.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
