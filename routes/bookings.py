from fastapi import APIRouter, HTTPException, status
from typing import List, Optional, Literal
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, validator

from models.bookings import BookingCreate, BookingOut
from models.user import UserInDB
from main import db

router = APIRouter()

# Utility to convert string id to ObjectId

def get_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")

# Mapping service_type to allowed specializations
SERVICE_SPEC_MAP = {
    'bereavement': ['bereavement'],
    'wellness': ['wellness', 'general wellbeing', 'bereavement'],  # bereavement specialists can also do wellness
}

# --- Create a new booking ---
@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking(booking: BookingCreate):
    # Verify consultant exists and has correct role
    consultant = await db.users.find_one({"_id": booking.consultant_id})
    if not consultant or consultant.get('role') != 'consultant':
        raise HTTPException(status_code=400, detail="Invalid consultant")
    # Check specialization matches service_type if required
    spec = consultant.get('specialization', '').lower()
    stype = booking.service_type
    if stype in SERVICE_SPEC_MAP:
        allowed_specs = SERVICE_SPEC_MAP[stype]
        if spec not in [s.lower() for s in allowed_specs]:
            raise HTTPException(
                status_code=400,
                detail=f"Consultant specialization '{consultant.get('specialization')}' does not match service_type '{stype}'"
            )
    # Prepare and insert booking
    doc = booking.dict(by_alias=True)
    doc['status'] = 'pending'
    doc['created_at'] = datetime.utcnow()
    doc['updated_at'] = datetime.utcnow()
    result = await db.bookings.insert_one(doc)
    created = await db.bookings.find_one({"_id": result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Booking creation failed")
    return created

# --- List bookings ---
@router.get("/", response_model=List[BookingOut])
async def list_bookings(user_id: Optional[str] = None, consultant_id: Optional[str] = None):
    query = {}
    if user_id:
        query['user_id'] = get_object_id(user_id)
    if consultant_id:
        query['consultant_id'] = get_object_id(consultant_id)
    cursor = db.bookings.find(query)
    bookings = []
    async for b in cursor:
        bookings.append(b)
    return bookings

# --- Get a single booking ---
@router.get("/{booking_id}", response_model=BookingOut)
async def get_booking(booking_id: str):
    oid = get_object_id(booking_id)
    booking = await db.bookings.find_one({"_id": oid})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking

# --- Consultant updates booking ---
class BookingUpdate(BaseModel):
    scheduled_time: Optional[datetime] = None
    meet_link: Optional[str] = None
    status: Optional[Literal['pending', 'confirmed', 'completed', 'cancelled']] = None

    @validator('scheduled_time')
    def must_be_future(cls, v: datetime):
        if v and v <= datetime.utcnow():
            raise ValueError('scheduled_time must be in the future')
        return v

@router.put("/{booking_id}", response_model=BookingOut)
async def update_booking(booking_id: str, update: BookingUpdate):
    oid = get_object_id(booking_id)
    existing = await db.bookings.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Booking not found")
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    update_data['updated_at'] = datetime.utcnow()
    result = await db.bookings.update_one({"_id": oid}, {"$set": update_data})
    if result.modified_count != 1:
        raise HTTPException(status_code=500, detail="Booking update failed")
    booking = await db.bookings.find_one({"_id": oid})
    return booking

# --- Cancel a booking ---
@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_booking(booking_id: str):
    oid = get_object_id(booking_id)
    result = await db.bookings.update_one({"_id": oid}, {"$set": {"status": "cancelled", "updated_at": datetime.utcnow()}})
    if result.matched_count != 1:
        raise HTTPException(status_code=404, detail="Booking not found")
    return None
