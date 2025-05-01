from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum
from bson import ObjectId

class EmergencyType(str, Enum):
    MEDICAL = "medical"
    ACCIDENT = "accident"
    CARDIAC = "cardiac"
    RESPIRATORY = "respiratory"
    OTHER = "other"

class EmergencyStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Location(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None

class EmergencyContact(BaseModel):
    name: str
    phone: str
    relationship: str

class EmergencyRequest(BaseModel):
    patient_id: str
    emergency_type: EmergencyType
    description: str
    location: Location
    contact_person: Optional[EmergencyContact] = None
    medical_notes: Optional[str] = None

class AmbulanceDetails(BaseModel):
    ambulance_id: str
    driver_name: str
    driver_phone: str
    vehicle_number: str
    estimated_arrival: Optional[datetime] = None

class EmergencyResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(ObjectId()))
    patient_id: str
    emergency_type: EmergencyType
    description: str
    location: Location
    status: EmergencyStatus = EmergencyStatus.PENDING
    contact_person: Optional[EmergencyContact] = None
    medical_notes: Optional[str] = None
    ambulance: Optional[AmbulanceDetails] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            ObjectId: str
        }
