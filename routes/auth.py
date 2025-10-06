from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Literal, Union
import bcrypt
import jwt
import os
import logging
import sys
from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Depends, Request, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator, validator
from bson import ObjectId
from jose import JWTError, jwt

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize logger
logger = logging.getLogger(__name__)

from models.user import UserCreate, UserInDB, UserOut
# Import db from database module instead of main to avoid circular imports
from database import db
from services.email_service import email_service

router = APIRouter()

# Password hashing settings
BCRYPT_SALT_ROUNDS = 12
MAX_PASSWORD_LENGTH = 72  # bcrypt's maximum password length

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET", "change_this_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    expires_in: int

class UserCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    username: str = Field(..., min_length=3, max_length=50)
    mobile_number: str = Field(..., pattern=r"^\+?[1-9]\d{1,14}$")
    password: str = Field(
        min_length=8,
        max_length=MAX_PASSWORD_LENGTH,
        pattern=r"^[A-Za-z\d@$!%*?&]{8,}$"
    )
    date_of_birth: date
    role: Literal['patient', 'consultant', 'admin'] = 'patient'
    specialization: Optional[str] = None
    access_code: Optional[str] = None

    @field_validator('password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c in "@$!%*?&" for c in v):
            raise ValueError('Password must contain at least one special character (@$!%*?&)')
        return v

@router.post("/signup", response_model=UserOut)
async def signup(user: UserCreate, background_tasks: BackgroundTasks, request: Request = None):
    # Log incoming request details for debugging
    logger.info(f"Incoming request: {request.method} {request.url}")
    if request:
        body = await request.body()
        logger.info(f"Request body: {body.decode() if body else 'Empty body'}")
    
    # Check if user already exists
    existing_user = await db.users.find_one({"$or": [
        {"email": user.email},
        {"username": user.username}
    ]})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered"
        )

    # Hash the password
    password_bytes = user.password.encode('utf-8')
    hashed_pw = bcrypt.hashpw(password_bytes, bcrypt.gensalt(BCRYPT_SALT_ROUNDS)).decode('utf-8')
    
    # Prepare user data for database
    user_dict = user.dict(exclude={"password", "access_code"})
    user_dict["hashed_password"] = hashed_pw
    user_dict["created_at"] = datetime.utcnow()
    user_dict["updated_at"] = datetime.utcnow()
    user_dict["is_active"] = True
    user_dict["is_verified"] = False
    
    # Handle role assignment based on access code
    if user.access_code:
        if user.access_code == '090808':
            user_dict["role"] = "admin"
        elif user.access_code == '070763':
            user_dict["role"] = "consultant"
            if not user.specialization:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Specialization is required for consultants"
                )
    
    # Create user in database
    try:
        logger.info(f"Creating user with data: {user_dict}")
        
        # Convert date to datetime for MongoDB before creating UserInDB
        if 'date_of_birth' in user_dict and isinstance(user_dict['date_of_birth'], date):
            from datetime import datetime as dt
            user_dict['date_of_birth'] = dt.combine(user_dict['date_of_birth'], dt.min.time())
        
        # Create the UserInDB instance with the processed date
        user_in_db = UserInDB(**user_dict)
        
        # Convert to dictionary for MongoDB, excluding None values
        user_data = {k: v for k, v in user_in_db.dict(by_alias=True).items() if v is not None}
        
        # Ensure all datetime objects are timezone-naive for MongoDB
        for key, value in user_data.items():
            if hasattr(value, 'isoformat'):  # Handles both date and datetime
                user_data[key] = value.isoformat()
        
        logger.info(f"Converted user data for DB: {user_data}")
        
        result = await db.users.insert_one(user_data)
        created_user = await db.users.find_one({"_id": result.inserted_id})
        logger.info(f"Successfully created user with ID: {result.inserted_id}")
        
    except Exception as e:
        import traceback
        error_details = f"Error creating user: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_details)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if 'duplicate key' in str(e) else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user account: {str(e)}" if 'duplicate key' not in str(e) else "Email or username already exists"
        )
    
    # Send welcome email in background
    try:
        background_tasks.add_task(
            email_service.send_welcome_email,
            user.email,
            user.first_name,
            user.last_name
        )
    except Exception as e:
        logger.error(f"Failed to queue welcome email task: {str(e)}")
        # Continue with user creation even if email fails
    
    return UserOut(**created_user)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

async def authenticate_user(username: str, password: str):
    user = await db.users.find_one({"$or": [{"username": username}, {"email": username}]})
    if not user:
        return False
    if not bcrypt.checkpw(password.encode('utf-8'), user["hashed_password"].encode('utf-8')):
        return False
    return user

@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None
):
    # Log incoming request
    logger.info(f"Login attempt for username: {form_data.username}")
    
    # Authenticate user
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token, expires_at = create_access_token(
        data={"sub": str(user["_id"])},
        expires_delta=access_token_expires
    )
    
    # Prepare user data for response (exclude sensitive info)
    user_data = {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "role": user["role"],
        "is_verified": user.get("is_verified", False)
    }
    
    logger.info(f"Successful login for user: {user['username']}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_data,
        "expires_in": int(access_token_expires.total_seconds())
    }

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        # Check token expiration
        exp = payload.get("exp")
        if not exp or datetime.utcnow() > datetime.fromtimestamp(exp):
            raise credentials_exception
            
    except (JWTError, jwt.PyJWTError) as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception
        
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise credentials_exception
        
    # Convert ObjectId to string for JSON serialization
    user["id"] = str(user["_id"])
    return user
