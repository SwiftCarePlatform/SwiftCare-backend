from fastapi import APIRouter, HTTPException, status
from typing import List, Optional, Literal
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, validator
import random

from models.bookings import BookingCreate, BookingOut
from models.user import UserInDB, PyObjectId
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

# --- Create a new booking (auto-assign consultant if not provided) ---
class BookingRequest(BaseModel):
    user_id: str
    service_type: Literal['bereavement', 'wellness', 'consultation', 'emergency']
    scheduled_time: datetime
    consultant_id: Optional[str] = None

    @validator('scheduled_time')
    def must_be_future(cls, v):
        if v <= datetime.now(timezone.utc):
            raise ValueError('scheduled_time must be in the future')
        return v

@router.post("/", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def create_booking(request: BookingRequest):
    # Convert user_id
    try:
        user_obj = get_object_id(request.user_id)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    # Determine consultant
    if request.consultant_id:
        # use provided consultant
        try:
            consultant_obj = get_object_id(request.consultant_id)
        except HTTPException:
            raise HTTPException(status_code=400, detail="Invalid consultant_id format")
    else:
        # Find eligible consultants
        spec_list = SERVICE_SPEC_MAP.get(request.service_type, [])
        # Query consultants with matching specialization
        cursor = db.users.find({
            'role': 'consultant',
            'specialization': {'$in': spec_list}
        })
        candidates = []
        async for cons in cursor:
            # check no existing booking at that time
            exists = await db.bookings.find_one({
                'consultant_id': cons['_id'],
                'scheduled_time': request.scheduled_time
            })
            if not exists:
                candidates.append(cons)
        if not candidates:
            raise HTTPException(status_code=404, detail="No available consultant for this time and service")
        # Randomly assign one
        picked = random.choice(candidates)
        consultant_obj = picked['_id']

    # Validate consultant role and specialization again
    consultant = await db.users.find_one({'_id': consultant_obj})
    if not consultant or consultant.get('role') != 'consultant':
        raise HTTPException(status_code=400, detail="Invalid consultant selected")
    # Prepare booking document
    doc = {
        'user_id': user_obj,
        'consultant_id': consultant_obj,
        'service_type': request.service_type,
        'scheduled_time': request.scheduled_time,
        'status': 'pending',
         'created_at': datetime.now(timezone.utc),
    'updated_at': datetime.now(timezone.utc),
        'meet_link': None
    }
    result = await db.bookings.insert_one(doc)
    booking = await db.bookings.find_one({'_id': result.inserted_id})
    if not booking:
        raise HTTPException(status_code=500, detail="Booking creation failed")
    return booking

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
        if v and v <= datetime.now(timezone.utc):
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
