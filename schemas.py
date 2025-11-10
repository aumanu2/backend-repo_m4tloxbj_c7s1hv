"""
Database Schemas for EduVerse – Coaching Management OS

Each Pydantic model below maps to a MongoDB collection with the lowercase
class name as the collection name. Example: Institution -> "institution".

These models validate incoming data for API endpoints.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Literal, Dict
from datetime import datetime

# Core tenancy
class Institution(BaseModel):
    name: str = Field(..., description="Institute name")
    subdomain: Optional[str] = Field(None, description="Optional unique subdomain/slug")
    plan: Literal["free", "basic", "premium", "enterprise"] = Field("free")
    contact_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class User(BaseModel):
    institution_id: str = Field(..., description="Institution ID (string _id)")
    role: Literal["admin", "teacher", "student", "parent"]
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = Field(None, description="Hashed or demo password placeholder")
    linked_student_id: Optional[str] = Field(None, description="If parent, link to student")

class Batch(BaseModel):
    institution_id: str
    name: str
    subject: Optional[str] = None
    teacher_ids: List[str] = Field(default_factory=list)
    schedule: Optional[str] = Field(None, description="Human-readable schedule")

class Student(BaseModel):
    institution_id: str
    user_id: str = Field(..., description="User record for the student")
    batch_ids: List[str] = Field(default_factory=list)
    admission_no: Optional[str] = None
    guardian_contact: Optional[str] = None
    meta: Dict[str, str] = Field(default_factory=dict)

# Attendance
class Attendance(BaseModel):
    institution_id: str
    student_id: str
    batch_id: Optional[str] = None
    date: str = Field(..., description="YYYY-MM-DD")
    status: Literal["present", "absent", "late"] = "present"
    mode: Literal["qr", "gps", "manual"] = "manual"
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    notes: Optional[str] = None

# Fees
class InvoiceItem(BaseModel):
    title: str
    amount: float

class Invoice(BaseModel):
    institution_id: str
    student_id: str
    currency: Literal["INR", "USD"] = "INR"
    items: List[InvoiceItem]
    gst_percent: float = 0.0
    status: Literal["unpaid", "partially_paid", "paid"] = "unpaid"
    due_date: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

class Payment(BaseModel):
    institution_id: str
    invoice_id: str
    amount: float
    method: Literal["upi", "wallet", "card", "cash"]
    provider: Optional[Literal["razorpay", "phonepe", "stripe", "manual"]] = None
    txn_ref: Optional[str] = None

# Tests
class Question(BaseModel):
    institution_id: str
    text: str
    options: List[str]
    correct_index: int
    topic: Optional[str] = None
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None

class Test(BaseModel):
    institution_id: str
    title: str
    question_ids: List[str]
    batch_id: Optional[str] = None
    duration_minutes: Optional[int] = None

class Submission(BaseModel):
    institution_id: str
    test_id: str
    student_id: str
    answers: List[int] = Field(..., description="Selected option index per question")

# Notifications (log only for MVP)
class Notification(BaseModel):
    institution_id: str
    user_id: str
    channel: Literal["sms", "whatsapp", "email", "push"]
    template: str
    payload: Dict[str, str] = Field(default_factory=dict)
    status: Literal["queued", "sent", "failed"] = "queued"

# Audit Log
class AuditLog(BaseModel):
    institution_id: str
    actor_user_id: Optional[str] = None
    action: str
    entity: str
    entity_id: Optional[str] = None
    diff: Dict[str, str] = Field(default_factory=dict)
    at: Optional[datetime] = None
