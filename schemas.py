"""
Pydantic schemas for the Lead Management CRM.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models import RoleEnum, LeadStatus


class UserCreate(BaseModel):
    """Schema for registering a new user."""
    username: str
    password: str
    role: RoleEnum


class UserOut(BaseModel):
    """Schema for returning user details."""
    id: int
    username: str
    role: RoleEnum

    class Config:
        """Pydantic config."""
        from_attributes = True


class Token(BaseModel):
    """Schema for returning JWT tokens."""
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Schema for decoding JWT tokens."""
    sub: Optional[str] = None
    role: Optional[str] = None


class LeadCreate(BaseModel):
    """Schema for creating a new lead."""
    name: str
    email: str
    phone: int = Field(..., ge=1000000000, le=9999999999, description="10-digit phone number")
    source: str


class LeadOut(BaseModel):
    """Schema for returning lead details."""
    id: int
    name: str
    email: str
    phone: int
    source: str
    status: LeadStatus
    assigned_to_id: Optional[int] = None
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class LeadUpdate(BaseModel):
    """Schema for updating an existing lead."""
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None
    reason: Optional[str] = None  # Reason required if escalating or manual reassign
    assigned_to_id: Optional[int] = None  # For manual reassignment
    version: int  # Concurrency control: must provide current expected version


class LeadActivityOut(BaseModel):
    """Schema for returning lead activity history."""
    id: int
    action: str
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    details: Optional[str] = None
    timestamp: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True


class FollowUpCreate(BaseModel):
    """Schema for creating a new follow-up."""
    scheduled_date: datetime
    notes: Optional[str] = None


class PaymentProofCreate(BaseModel):
    """Schema for uploading payment proofs."""
    file_url: str


class StudentOut(BaseModel):
    """Schema for returning student enrollment details."""
    id: int
    name: str
    email: str
    course: Optional[str] = None
    enrolled_at: datetime

    class Config:
        """Pydantic config."""
        from_attributes = True
