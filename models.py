"""
Database models for the Lead Management System.
"""
import datetime
import enum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, BigInteger
from sqlalchemy.orm import relationship

from database import Base

class RoleEnum(str, enum.Enum):
    """User roles enum."""
    ADMIN = "Admin"
    COUNSELLOR = "Counsellor"
    TELECALLER = "Telecaller"

class LeadStatus(str, enum.Enum):
    """Lead statuses enum."""
    NEW = "New"
    IN_PROGRESS = "InProgress"
    FOLLOW_UP = "FollowUp"
    ESCALATED = "Escalated"
    PAYMENT_PENDING = "PaymentPending"
    CONVERTED = "Converted"
    DEAD = "Dead"

class User(Base):
    """User model representing a staff member."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(SQLEnum(RoleEnum))

    leads = relationship("Lead", back_populates="assignee")

class Lead(Base):
    """Lead model representing a potential student."""
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(BigInteger)
    source = Column(String)
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.NEW)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow,
                        onupdate=datetime.datetime.utcnow)
    version = Column(Integer, default=1)  # Optimistic concurrency control

    assignee = relationship("User", back_populates="leads")
    activities = relationship("LeadActivity", back_populates="lead")
    followups = relationship("FollowUp", back_populates="lead")
    payments = relationship("PaymentProof", back_populates="lead")
    student_profile = relationship("Student", uselist=False, back_populates="origin_lead")

class LeadActivity(Base):
    """Audit log of activities performed on a lead."""
    __tablename__ = "lead_activities"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String) # CREATE, STATUS_CHANGE, NOTE, ESCALATE, REASSIGN
    previous_state = Column(String, nullable=True)
    new_state = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    lead = relationship("Lead", back_populates="activities")

class FollowUp(Base):
    """Scheduled follow-up for a lead."""
    __tablename__ = "follow_ups"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    scheduled_date = Column(DateTime)
    status = Column(String, default="Pending") # Pending, Completed
    notes = Column(Text, nullable=True)

    lead = relationship("Lead", back_populates="followups")

class PaymentProof(Base):
    """Payment proof record with versioning."""
    __tablename__ = "payment_proofs"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    file_url = Column(String)
    version = Column(Integer, default=1)
    status = Column(String, default="Pending") # Pending, Verified, Rejected
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    lead = relationship("Lead", back_populates="payments")

class Student(Base):
    """Converted student model with original lead reference."""
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), unique=True)
    name = Column(String)
    email = Column(String)
    phone = Column(BigInteger)
    locked_data = Column(Text) # JSON snapshot of data
    enrolled_at = Column(DateTime, default=datetime.datetime.utcnow)

    origin_lead = relationship("Lead", back_populates="student_profile")
