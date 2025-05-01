from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum
from bson import ObjectId

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class PaymentBase(BaseModel):
    amount: float = Field(..., gt=0)
    email: EmailStr
    booking_id: str
    currency: str = "NGN"
    description: Optional[str] = None

class PaymentCreate(PaymentBase):
    reference: Optional[str] = None

class PaymentDB(PaymentBase):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    reference: str
    status: PaymentStatus = PaymentStatus.PENDING
    authorization_url: Optional[str] = None
    access_code: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            ObjectId: str
        }

class PaymentResponse(PaymentDB):
    pass
