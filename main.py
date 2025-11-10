import os
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId

from database import db, create_document, get_documents
from schemas import Institution, User, Batch, Student, Attendance, Invoice, Payment, Question, Test, Submission, Notification, AuditLog, InvoiceItem

app = FastAPI(title="EduVerse – Coaching Management OS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers
class IdResponse(BaseModel):
    id: str

def to_oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")

# Health
@app.get("/")
def root():
    return {"name": "EduVerse API", "status": "ok"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:20]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# -----------------
# Institution & Users
# -----------------
@app.post("/institutions", response_model=IdResponse)
def create_institution(payload: Institution):
    ins_id = create_document("institution", payload)
    return {"id": ins_id}

@app.get("/institutions")
def list_institutions():
    return get_documents("institution")

@app.post("/users", response_model=IdResponse)
def create_user(payload: User):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    # simple uniqueness guard for demo
    if payload.email:
        existing = db["user"].find_one({"email": payload.email, "institution_id": payload.institution_id})
        if existing:
            raise HTTPException(status_code=409, detail="Email already exists in institution")
    uid = create_document("user", payload)
    return {"id": uid}

@app.get("/users")
def list_users(institution_id: Optional[str] = None, role: Optional[str] = None):
    filt: Dict = {}
    if institution_id:
        filt["institution_id"] = institution_id
    if role:
        filt["role"] = role
    return get_documents("user", filt)

# -----------------
# Batches & Students
# -----------------
@app.post("/batches", response_model=IdResponse)
def create_batch(payload: Batch):
    bid = create_document("batch", payload)
    return {"id": bid}

@app.get("/batches")
def list_batches(institution_id: Optional[str] = None):
    return get_documents("batch", {"institution_id": institution_id} if institution_id else {})

@app.post("/students", response_model=IdResponse)
def create_student(payload: Student):
    sid = create_document("student", payload)
    return {"id": sid}

@app.get("/students")
def list_students(institution_id: Optional[str] = None, batch_id: Optional[str] = None):
    q: Dict = {}
    if institution_id:
        q["institution_id"] = institution_id
    if batch_id:
        q["batch_ids"] = {"$in": [batch_id]}
    return get_documents("student", q)

# -----------------
# Attendance
# -----------------
@app.post("/attendance", response_model=IdResponse)
def mark_attendance(payload: Attendance):
    aid = create_document("attendance", payload)
    # naive notification log for absent
    if db is not None and payload.status == "absent":
        notif = Notification(
            institution_id=payload.institution_id,
            user_id=payload.student_id,
            channel="push",
            template="absence_alert",
            payload={"date": payload.date},
            status="queued",
        )
        create_document("notification", notif)
    return {"id": aid}

@app.get("/attendance")
def list_attendance(institution_id: str, student_id: Optional[str] = None, date: Optional[str] = None):
    q: Dict = {"institution_id": institution_id}
    if student_id:
        q["student_id"] = student_id
    if date:
        q["date"] = date
    return get_documents("attendance", q)

# -----------------
# Invoices & Payments
# -----------------
class CreateInvoiceRequest(BaseModel):
    institution_id: str
    student_id: str
    items: List[InvoiceItem]
    gst_percent: float = 0.0
    currency: Optional[str] = "INR"
    due_date: Optional[str] = None

@app.post("/invoices", response_model=IdResponse)
def create_invoice(payload: CreateInvoiceRequest):
    inv = Invoice(
        institution_id=payload.institution_id,
        student_id=payload.student_id,
        currency=payload.currency or "INR",
        items=payload.items,
        gst_percent=payload.gst_percent,
        status="unpaid",
        due_date=payload.due_date,
    )
    inv_id = create_document("invoice", inv)
    return {"id": inv_id}

@app.get("/invoices")
def list_invoices(institution_id: str, student_id: Optional[str] = None):
    q: Dict = {"institution_id": institution_id}
    if student_id:
        q["student_id"] = student_id
    return get_documents("invoice", q)

class RecordPaymentRequest(BaseModel):
    institution_id: str
    invoice_id: str
    amount: float
    method: str
    provider: Optional[str] = None
    txn_ref: Optional[str] = None

@app.post("/payments", response_model=IdResponse)
def record_payment(payload: RecordPaymentRequest):
    pay = Payment(
        institution_id=payload.institution_id,
        invoice_id=payload.invoice_id,
        amount=payload.amount,
        method=payload.method,  # upi/wallet/card/cash
        provider=payload.provider,  # razorpay/phonepe/stripe/manual
        txn_ref=payload.txn_ref,
    )
    pid = create_document("payment", pay)
    # mark invoice status naively (paid if amounts cover)
    if db is not None:
        inv = db["invoice"].find_one({"_id": to_oid(payload.invoice_id)})
        if inv:
            paid_total = sum([p.get("amount", 0) for p in db["payment"].find({"invoice_id": payload.invoice_id})])
            items_total = sum([it.get("amount", 0) for it in inv.get("items", [])])
            gst = inv.get("gst_percent", 0) * items_total / 100
            due = items_total + gst
            status = "paid" if paid_total >= due - 1e-2 else ("partially_paid" if paid_total > 0 else "unpaid")
            db["invoice"].update_one({"_id": inv["_id"]}, {"$set": {"status": status}})
    return {"id": pid}

# -----------------
# Tests (simple)
# -----------------
@app.post("/questions", response_model=IdResponse)
def create_question(payload: Question):
    qid = create_document("question", payload)
    return {"id": qid}

@app.post("/tests", response_model=IdResponse)
def create_test(payload: Test):
    tid = create_document("test", payload)
    return {"id": tid}

@app.post("/submissions", response_model=IdResponse)
def submit_test(payload: Submission):
    sid = create_document("submission", payload)
    return {"id": sid}

@app.get("/analytics/attendance/trend")
def attendance_trend(institution_id: str, student_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    pipeline = [
        {"$match": {"institution_id": institution_id, "student_id": student_id}},
        {"$group": {"_id": "$date", "present": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}}, "total": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    data = list(db["attendance"].aggregate(pipeline))
    return {"series": data}

# Schema viewer for admin tools
@app.get("/schema")
def get_schema_definitions():
    from inspect import getmembers, isclass
    import schemas as s
    models = {name: cls.model_json_schema() for name, cls in getmembers(s) if isclass(cls) and issubclass(cls, BaseModel)}
    return models

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
