from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
import datetime
from database import Base

class RoleEnum(str, enum.Enum):
    Admin = "Admin"
    Counsellor = "Counsellor"
    Telecaller = "Telecaller"

class LeadStatus(str, enum.Enum):
    New = "New"
    InProgress = "InProgress"
    FollowUp = "FollowUp"
    Escalated = "Escalated"
    PaymentPending = "PaymentPending"
    Converted = "Converted"
    Dead = "Dead"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(Enum(RoleEnum))

    leads = relationship("Lead", back_populates="assignee")

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    source = Column(String)
    status = Column(Enum(LeadStatus), default=LeadStatus.New)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    version = Column(Integer, default=1)  # Optimistic concurrency control

    assignee = relationship("User", back_populates="leads")
    activities = relationship("LeadActivity", back_populates="lead")
    followups = relationship("FollowUp", back_populates="lead")
    payments = relationship("PaymentProof", back_populates="lead")
    student_profile = relationship("Student", uselist=False, back_populates="origin_lead")

class LeadActivity(Base):
    __tablename__ = "lead_activities"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String) # CREATE, STATUS_CHANGE, NOTE, ESCALATE, REASSIGN
    previous_state = Column(String, nullable=True)
    new_state = Column(String, nullable=True)
    details = Column(Text, nullable=True)  # Includes reasons or notes
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    lead = relationship("Lead", back_populates="activities")

class FollowUp(Base):
    __tablename__ = "follow_ups"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    scheduled_date = Column(DateTime)
    status = Column(String, default="Pending") # Pending, Completed
    notes = Column(Text, nullable=True)

    lead = relationship("Lead", back_populates="followups")

class PaymentProof(Base):
    __tablename__ = "payment_proofs"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    file_url = Column(String)
    version = Column(Integer, default=1)
    status = Column(String, default="Pending") # Pending, Verified, Rejected
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    lead = relationship("Lead", back_populates="payments")

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), unique=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    locked_data = Column(Text) # JSON snapshot of data
    enrolled_at = Column(DateTime, default=datetime.datetime.utcnow)

    origin_lead = relationship("Lead", back_populates="student_profile")
