"""
CRUD operations for the Lead Management System.
"""
import json
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models import User, Lead, LeadActivity, RoleEnum, LeadStatus, PaymentProof, Student
from schemas import LeadCreate, LeadUpdate, UserCreate
from auth import get_password_hash

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

def log_activity(db: Session, lead_id: int, user_id: int, action: str,
                 prev_state: str = None, new_state: str = None, details: str = None):
    """Log an activity event for a specific lead."""
    activity = LeadActivity(
        lead_id=lead_id,
        user_id=user_id,
        action=action,
        previous_state=prev_state,
        new_state=new_state,
        details=details
    )
    db.add(activity)

def auto_assign_lead(db: Session):
    """Auto-assign a lead to a telecaller or counsellor."""
    # Simple round-robin logic: find Telecaller with fewest leads in non-terminal states
    # For now, just pick the first Telecaller or Counsellor
    telecaller = db.query(User).filter(User.role == RoleEnum.TELECALLER).first()
    if telecaller:
        return telecaller.id
    # Fallback to counsellor
    counsellor = db.query(User).filter(User.role == RoleEnum.COUNSELLOR).first()
    return counsellor.id if counsellor else None

def create_lead(db: Session, lead: LeadCreate, current_user: User):
    """Create a new lead and auto-assign."""
    new_lead = Lead(
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        source=lead.source,
        status=LeadStatus.NEW
    )
    new_lead.assigned_to_id = auto_assign_lead(db)

    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)

    log_activity(
        db, new_lead.id, current_user.id, "CREATE",
        new_state=new_lead.status.value, details="Lead created"
    )
    db.commit()
    return new_lead

def get_leads(db: Session, current_user: User):
    """Retrieve leads based on user role."""
    if current_user.role == RoleEnum.ADMIN:
        return db.query(Lead).all()
    # Telecaller/Counsellor can only see assigned leads
    return db.query(Lead).filter(Lead.assigned_to_id == current_user.id).all()

def update_lead(db: Session, lead_id: int, lead_update: LeadUpdate, current_user: User):
    """Update a lead's status, notes, or assignment securely."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Check permissions
    if current_user.role != RoleEnum.ADMIN and lead.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this lead")

    # Concurrency / Version check
    if lead.version != lead_update.version:
        raise HTTPException(status_code=409, detail="Concurrent update. Refresh and try again.")

    prev_state = lead.status.value
    notes_added = ""

    # Status Transition Check
    if lead_update.status and lead_update.status != lead.status:
        # Rules configuration
        if lead.status in [LeadStatus.CONVERTED, LeadStatus.DEAD]:
            raise HTTPException(status_code=400, detail="Cannot change Converted/Dead leads")

        # Escalate Rules
        if lead_update.status == LeadStatus.ESCALATED:
            if not lead_update.reason:
                raise HTTPException(status_code=400, detail="Reason required to escalate lead")
            notes_added += f"Escalated. Reason: {lead_update.reason} "

            # Reassign to a counsellor if current is telecaller
            if current_user.role == RoleEnum.TELECALLER:
                counsellor = db.query(User).filter(User.role == RoleEnum.COUNSELLOR).first()
                if counsellor:
                    lead.assigned_to_id = counsellor.id
                    notes_added += f"(Auto-assigned to Counsellor ID {counsellor.id})"

        lead.status = lead_update.status
        log_activity(
            db, lead.id, current_user.id, "STATUS_CHANGE",
            prev_state=prev_state, new_state=lead.status.value, details=notes_added
        )

    # Manual Reassignment
    if lead_update.assigned_to_id and current_user.role in [RoleEnum.ADMIN, RoleEnum.COUNSELLOR]:
        if not lead_update.reason:
            raise HTTPException(status_code=400, detail="Reason required for manual reassignment")
        old_assignee = lead.assigned_to_id
        lead.assigned_to_id = lead_update.assigned_to_id
        details = (f"From {old_assignee} to {lead_update.assigned_to_id}. "
                   f"Reason: {lead_update.reason}")
        log_activity(
            db, lead.id, current_user.id, "REASSIGNED",
            details=details
        )

    # Generic Notes Update
    if lead_update.notes:
        log_activity(db, lead.id, current_user.id, "NOTE", details=lead_update.notes)

    # Increment Version
    lead.version += 1
    db.commit()
    db.refresh(lead)
    return lead

def convert_lead(db: Session, lead_id: int, current_user: User):
    """Convert a lead to a student if they have verified payments."""
    if current_user.role == RoleEnum.TELECALLER:
        raise HTTPException(status_code=403, detail="Telecallers cannot convert leads")

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead or lead.status == LeadStatus.CONVERTED:
        raise HTTPException(status_code=400, detail="Invalid lead to convert")

    # Payment Verification rule check could go here
    proof = db.query(PaymentProof).filter(
        PaymentProof.lead_id == lead_id,
        PaymentProof.status == "Verified"
    ).first()

    if not proof:
        raise HTTPException(status_code=400, detail="No verified payment found, cannot convert.")

    # Create Student Record & lock data
    locked_data = json.dumps({
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "source": lead.source
    })
    student = Student(
        lead_id=lead_id, name=lead.name, email=lead.email,
        phone=lead.phone, locked_data=locked_data
    )

    prev_state = lead.status.value
    lead.status = LeadStatus.CONVERTED
    log_activity(
        db, lead.id, current_user.id, "CONVERTED",
        prev_state=prev_state, new_state=LeadStatus.CONVERTED.value,
        details="Converted to Student"
    )

    db.add(student)
    db.commit()
    db.refresh(lead)
    return lead
