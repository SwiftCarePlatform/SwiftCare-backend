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

# Rate limiting and security settings
MAX_SIGNUP_ATTEMPTS = 5
SIGNUP_WINDOW = 3600  # 1 hour in seconds
LOGIN_ATTEMPTS = {}
LOGIN_WINDOW = 300  # 5 minutes in seconds

class UserExistsError(HTTPException):
    def __init__(self, field: str, value: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with this {field} already exists: {value}"
        )

class RateLimitExceeded(HTTPException):
    def __init__(self, retry_after: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after_seconds": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )

async def check_rate_limit(ip: str, endpoint: str, max_attempts: int, window: int):
    """Check if the request exceeds the rate limit."""
    current_time = datetime.utcnow().timestamp()
    key = f"{ip}:{endpoint}"
    
    if key in LOGIN_ATTEMPTS:
        attempts = [t for t in LOGIN_ATTEMPTS[key] if current_time - t < window]
        if len(attempts) >= max_attempts:
            retry_after = int(window - (current_time - attempts[0]))
            raise RateLimitExceeded(retry_after)
        attempts.append(current_time)
        LOGIN_ATTEMPTS[key] = attempts
    else:
        LOGIN_ATTEMPTS[key] = [current_time]

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(
    user: UserCreate, 
    background_tasks: BackgroundTasks, 
    request: Request = None
):
    """
    Register a new user account.
    
    - **email**: Must be a valid email address
    - **password**: Must be at least 8 characters long, contain at least one uppercase,
      one lowercase, one digit, and one special character (@$!%*?&)
    - **username**: Must be 3-50 characters long
    - **mobile_number**: Must be in E.164 format (e.g., +1234567890)
    - **date_of_birth**: Must be a valid date in the past
    - **role**: Must be one of 'patient', 'consultant', or 'admin'
    - **specialization**: Required if role is 'consultant'
    - **access_code**: Required for 'admin' or 'consultant' roles
    """
    client_ip = request.client.host if request and request.client else "unknown"
    
    try:
        # Rate limiting check
        await check_rate_limit(client_ip, "signup", MAX_SIGNUP_ATTEMPTS, SIGNUP_WINDOW)
        
        # Log incoming request
        logger.info(f"Signup attempt - IP: {client_ip}, Email: {user.email}, Username: {user.username}")
        
        # Check if user already exists
        existing_email = await db.users.find_one({"email": user.email.lower()})
        if existing_email:
            raise UserExistsError("email", user.email)
            
        existing_username = await db.users.find_one({"username": user.username.lower()})
        if existing_username:
            raise UserExistsError("username", user.username)
        
        # Validate role and access code
        if user.role in ["admin", "consultant"] and not user.access_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Access code is required for {user.role} registration"
            )
            
        if user.role == "consultant" and not user.specialization:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Specialization is required for consultant role"
            )
        
        password_bytes = user.password.encode('utf-8')
        hashed_pw = bcrypt.hashpw(password_bytes, bcrypt.gensalt(BCRYPT_SALT_ROUNDS)).decode('utf-8')
        
        # Prepare user data for database
        user_dict = user.dict(exclude={"password", "access_code"})
        
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
        
        # Set hashed password and timestamps
        user_dict.update({
            "hashed_password": hashed_pw,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_active": True,
            "is_verified": False
        })
        
        # Create user in database
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

async def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user with username/email and password.
    
    Args:
        username: Username or email of the user
        password: Plain text password
        
    Returns:
        User document if authentication is successful, None otherwise
    """
    try:
        # Case-insensitive search for username/email
        user = await db.users.find_one({
            "$or": [
                {"username": username.lower()},
                {"email": username.lower()}
            ]
        })
        
        if not user:
            # Simulate password check to prevent timing attacks
            bcrypt.checkpw(
                b"dummy_password", 
                bcrypt.gensalt().encode('utf-8')
            )
            return None
            
        # Verify password
        if not bcrypt.checkpw(
            password.encode('utf-8'), 
            user["hashed_password"].encode('utf-8')
        ):
            return None
            
        return user
        
    except Exception as e:
        logger.error(f"Authentication error for user {username}: {str(e)}", exc_info=True)
        return None

class LoginError(HTTPException):
    def __init__(self, 
        status_code: int, 
        error_code: str, 
        detail: str, 
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            status_code=status_code,
            detail={
                "error": error_code,
                "message": detail
            },
            headers=headers or {}
        )

@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None
):
    """
    OAuth2 compatible token login.
    
    - **username**: Your email or username
    - **password**: Your password
    
    Returns an access token and user information.
    
    Error Responses:
    - 400: Invalid request format
    - 401: Invalid credentials
    - 403: Account inactive, email not verified, or access denied
    - 423: Account locked
    - 429: Too many login attempts
    - 500: Internal server error
    """
    client_ip = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")
    
    try:
        # Input validation
        if not form_data.username or not form_data.password:
            raise LoginError(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="missing_credentials",
                detail="Both username and password are required"
            )
            
        # Rate limiting check (separate for IP and username to prevent enumeration)
        try:
            await check_rate_limit(
                f"login:ip:{client_ip}",
                "login_ip",
                max_attempts=10,
                window=300  # 5 minutes
            )
            await check_rate_limit(
                f"login:user:{form_data.username.lower()}",
                "login_user",
                max_attempts=5,
                window=300  # 5 minutes
            )
        except RateLimitExceeded as e:
            logger.warning(f"Rate limit exceeded - IP: {client_ip}, Username: {form_data.username}")
            retry_after = int(e.retry_after_seconds)
            raise LoginError(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                error_code="too_many_attempts",
                detail=f"Too many login attempts. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )
        
        # Log login attempt
        logger.info(f"Login attempt - IP: {client_ip}, User-Agent: {user_agent}, Username: {form_data.username}")
        
        # Authenticate user
        try:
            user = await authenticate_user(form_data.username, form_data.password)
            if not user:
                raise LoginError(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    error_code="invalid_credentials",
                    detail="Incorrect username or password"
                )
                
            # Initialize or get login_attempts with a default of 0 if None
            login_attempts = user.get("login_attempts", 0)
            
            # Safely get lock_until, defaulting to minimum datetime
            lock_until = user.get("lock_until")
            if lock_until is None or not isinstance(lock_until, datetime):
                lock_until = datetime.min
            
            # Check if account is locked
            current_time = datetime.utcnow()
            if login_attempts >= 5 and lock_until > current_time:
                    lock_time = (lock_until - current_time).seconds // 60
                    raise LoginError(
                        status_code=status.HTTP_423_LOCKED,
                        error_code="account_locked",
                        detail=f"Account locked due to too many failed attempts. Try again in {lock_time} minutes."
                    )
            
            # Check if user is active
            if not user.get("is_active", True):
                raise LoginError(
                    status_code=status.HTTP_403_FORBIDDEN,
                    error_code="account_inactive",
                    detail="This account has been deactivated. Please contact support for assistance."
                )
            
            # Check if email is verified
            if not user.get("is_verified", False):
                raise LoginError(
                    status_code=status.HTTP_403_FORBIDDEN,
                    error_code="email_not_verified",
                    detail="Please verify your email address before logging in. Check your inbox for the verification link."
                )
                
            # Reset failed login attempts on successful login
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"login_attempts": 0, "last_login": datetime.utcnow()}}
            )
            
        except LoginError:
            # Update failed login attempts
            if user and "_id" in user:
                await db.users.update_one(
                    {"_id": user["_id"]},
                    [
                        {
                            "$set": {
                                "login_attempts": {"$add": ["$login_attempts", 1]},
                                "last_failed_attempt": datetime.utcnow(),
                                "lock_until": {
                                    "$cond": [
                                        {"$gte": ["$login_attempts", 4]},  # After 5th failed attempt
                                        {"$add": ["$$NOW", 30 * 60 * 1000]},  # Lock for 30 minutes
                                        None
                                    ]
                                }
                            }
                        }
                    ]
                )
            raise
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token, expires_at = create_access_token(
            data={"sub": str(user["_id"])},
            expires_delta=access_token_expires
        )
        
        # Prepare user data for response
        user_data = {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user["email"],
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "role": user["role"],
            "is_verified": user.get("is_verified", False)
        }
        
        # Log successful login
        logger.info(f"Successful login - User ID: {user_data['id']}, IP: {client_ip}")
        
        # Add security headers
        response_headers = {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "X-XSS-Protection": "1; mode=block"
        }
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": user_data,
            "expires_in": int(access_token_expires.total_seconds())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login - IP: {client_ip}, Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later."
        )

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
