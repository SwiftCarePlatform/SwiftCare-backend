from pydantic import BaseModel, Field, validator
from typing import Literal, Optional
from datetime import datetime
from bson import ObjectId

from models.user import PyObjectId


class BookingBase(BaseModel):
    user_id: PyObjectId = Field(..., alias="user_id")
    consultant_id: PyObjectId = Field(..., alias="consultant_id")
    service_type: Literal['consultation', 'bereavement', 'emergency', 'wellness']
    scheduled_time: datetime
    meet_link: Optional[str] = None

    @validator('scheduled_time')
    def must_be_future(cls, v: datetime):
        if v <= datetime.utcnow():
            raise ValueError('scheduled_time must be in the future')
        return v


class BookingCreate(BookingBase):
    pass  # inherits fields for creating a booking


class BookingInDB(BookingBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    status: Literal['pending', 'confirmed', 'completed', 'cancelled'] = 'pending'
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}


class BookingOut(BookingBase):
    id: PyObjectId = Field(alias="_id")
    status: Literal['pending', 'confirmed', 'completed', 'cancelled']
    meet_link: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, datetime: lambda v: v.isoformat()}
