from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Depends
from pydantic import BaseModel, EmailStr, Field, validator, constr
import bcrypt
import jwt, os, datetime
import logging
from fastapi.security import OAuth2PasswordBearer
import sys
import os
from typing import Optional

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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: constr(
        min_length=8,
        max_length=MAX_PASSWORD_LENGTH,
        regex=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]$",
    )

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate, background_tasks: BackgroundTasks):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password with bcrypt directly
    password_bytes = user.password.encode('utf-8')
    hashed_pw = bcrypt.hashpw(password_bytes, bcrypt.gensalt(BCRYPT_SALT_ROUNDS)).decode('utf-8')
    
    # Create user in database
    user_dict = user.dict(exclude={"password"})
    user_dict['hashed_password'] = hashed_pw
    user_in_db = UserInDB(**user_dict)
    
    doc = user_in_db.dict(by_alias=True)
    dob = doc.get('dob')
    if isinstance(dob, datetime.date):
        doc['dob'] = datetime.datetime(dob.year, dob.month, dob.day)
    
    result = await db.users.insert_one(doc)
    created = await db.users.find_one({"_id": result.inserted_id})
    
    # Send welcome email in the background
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
    
    return created

@router.post("/login", response_model=Token)
async def login(login_req: LoginRequest):
    user = await db.users.find_one({"email": login_req.email})
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    user_in_db = UserInDB(**user)
    if not bcrypt.checkpw(login_req.password.encode('utf-8'), user_in_db.hashed_password.encode('utf-8')):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_in_db.id), "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

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
        if not exp or datetime.datetime.utcnow() > datetime.datetime.fromtimestamp(exp):
            raise credentials_exception
            
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = await db.users.find_one({"_id": user_id})
    if user is None:
        raise credentials_exception
    return user
