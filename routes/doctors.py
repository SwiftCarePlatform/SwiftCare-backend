from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime, time, timedelta
from bson import ObjectId
from pydantic import BaseModel, Field, validator
import logging
from typing_extensions import Annotated

# Import database and models
from database import db
from models.user import UserInDB, UserOut
from auth_utils import get_current_active_user, UserRole

router = APIRouter(prefix="/doctors", tags=["doctors"])
logger = logging.getLogger(__name__)

# Models
class DoctorUpdate(BaseModel):
    bio: Optional[str] = None
    consultation_fee: Optional[float] = Field(None, gt=0)
    availability: Optional[Dict[str, List[str]]] = None  # e.g., {"monday": ["09:00", "17:00"], ...}
    specialization: Optional[str] = None
    qualifications: Optional[List[str]] = None
    experience_years: Optional[int] = Field(None, ge=0)
    languages: Optional[List[str]] = None
    is_available: Optional[bool] = True

class DoctorOut(UserOut):
    bio: Optional[str] = None
    consultation_fee: Optional[float] = None
    availability: Dict[str, List[str]] = {}
    qualifications: List[str] = []
    experience_years: Optional[int] = None
    languages: List[str] = []
    is_available: bool = True

    class Config:
        json_encoders = {ObjectId: str}
        from_attributes = True

# Helper function to check if user is a doctor
async def get_doctor(doctor_id: str) -> Dict[str, Any]:
    try:
        doctor = await db.users.find_one({
            "_id": ObjectId(doctor_id),
            "role": "consultant"
        })
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")
        return doctor
    except:
        raise HTTPException(status_code=400, detail="Invalid doctor ID")

# Update doctor profile
@router.put("/{doctor_id}", response_model=DoctorOut)
async def update_doctor_profile(
    doctor_id: str,
    update_data: DoctorUpdate,
    current_user: UserInDB = Depends(get_current_active_user)
):
    # Only allow doctors to update their own profile or admin
    if str(current_user.id) != doctor_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this doctor's profile"
        )
    
    # Get the doctor
    doctor = await get_doctor(doctor_id)
    
    # Prepare update data
    update_dict = update_data.dict(exclude_unset=True)
    update_dict["updated_at"] = datetime.utcnow()
    
    # Update in database
    result = await db.users.update_one(
        {"_id": ObjectId(doctor_id)},
        {"$set": update_dict}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update doctor profile")
    
    # Return updated doctor
    updated_doctor = await db.users.find_one({"_id": ObjectId(doctor_id)})
    return DoctorOut(**updated_doctor)

# Search and filter doctors
@router.get("/search", response_model=List[DoctorOut])
async def search_doctors(
    specialization: Optional[str] = None,
    min_experience: Optional[int] = None,
    max_fee: Optional[float] = None,
    language: Optional[str] = None,
    available: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 10,
    skip: int = 0
):
    # Build query
    query = {"role": "consultant"}
    
    if specialization:
        query["specialization"] = {"$regex": specialization, "$options": "i"}
    
    if min_experience is not None:
        query["experience_years"] = {"$gte": min_experience}
    
    if max_fee is not None:
        query["consultation_fee"] = {"$lte": max_fee}
    
    if language:
        query["languages"] = {"$in": [language]}
    
    if available is not None:
        query["is_available"] = available
    
    if search:
        query["$or"] = [
            {"first_name": {"$regex": search, "$options": "i"}},
            {"last_name": {"$regex": search, "$options": "i"}},
            {"bio": {"$regex": search, "$options": "i"}}
        ]
    
    # Execute query
    cursor = db.users.find(query).skip(skip).limit(limit)
    doctors = []
    
    async for doc in cursor:
        doctors.append(DoctorOut(**doc))
    
    return doctors

# Get doctor availability
@router.get("/{doctor_id}/availability")
async def get_doctor_availability(doctor_id: str):
    doctor = await get_doctor(doctor_id)
    return {
        "availability": doctor.get("availability", {}),
        "is_available": doctor.get("is_available", True)
    }
