from pydantic import BaseModel, EmailStr, Field, validator, root_validator
from typing import Literal, Optional
from datetime import date
from bson import ObjectId


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    mobile_number: str = Field(..., regex=r"^\+?[1-9]\d{1,14}$")
    email: EmailStr
    dob: date
    role: Literal['patient', 'consultant', 'admin'] = 'patient'

    @validator('dob')
    def dob_in_past(cls, v: date):
        if v >= date.today():
            raise ValueError('dob must be in the past')
        return v


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    access_code: Optional[str] = None

    @root_validator(pre=True)
    def assign_role_by_access_code(cls, values):
        code = values.get('access_code')
        if code == '090808':
            values['role'] = 'admin'
        elif code == '070763':
            values['role'] = 'consultant'
        else:
            values['role'] = 'patient'
        return values


class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class UserOut(UserBase):
    id: PyObjectId = Field(alias="_id")

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
