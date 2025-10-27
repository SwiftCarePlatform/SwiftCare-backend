from pydantic import BaseModel, EmailStr, Field, validator, root_validator
from typing import Literal, Optional, Any
from datetime import date, datetime
from bson import ObjectId

# Pydantic version compatibility
try:
    # Pydantic v2
    from pydantic_core import core_schema
    from pydantic import GetCoreSchemaHandler
    PYDANTIC_V2 = True
except ImportError:
    # Pydantic v1
    PYDANTIC_V2 = False

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    # Pydantic v2 compatibility
    if PYDANTIC_V2:
        @classmethod
        def __get_pydantic_core_schema__(
            cls, _source_type: Any, _handler: GetCoreSchemaHandler
        ) -> core_schema.CoreSchema:
            return core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.no_info_plain_validator_function(cls.validate),
            ])

        @classmethod
        def __get_pydantic_json_schema__(cls, _core_schema, handler):
            return handler(core_schema.str_schema())


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    mobile_number: str = Field(..., pattern=r"^\+?[1-9]\d{1,14}$")
    email: EmailStr
    date_of_birth: date
    role: Literal['patient', 'consultant', 'admin'] = 'patient'
    specialization: Optional[str] = None

    @validator('date_of_birth')
    def date_of_birth_in_past(cls, v: date):
        if v >= date.today():
            raise ValueError('Date of birth must be in the past')
        return v


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    access_code: Optional[str] = None

    @root_validator(pre=True)
    def assign_role_and_require_specialization(cls, values):
        code = values.get('access_code')
        # Assign role based on access code
        if code == '090808':
            values['role'] = 'admin'
        elif code == '070763':
            values['role'] = 'consultant'
        else:
            values['role'] = 'patient'
        # If consultant, require specialization
        if values.get('role') == 'consultant':
            spec = values.get('specialization')
            if not spec:
                raise ValueError('specialization is required for consultants')
        return values


class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    is_verified: bool = True

    class Config:
        json_encoders = {ObjectId: str}
        arbitrary_types_allowed = True
        validate_by_name = True

class UserOut(UserBase):
    id: PyObjectId = Field(alias="_id")

    model_config = {
        "validate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }
