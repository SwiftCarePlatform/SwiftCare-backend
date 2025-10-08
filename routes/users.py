from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
import os
import logging

from database import db
from models.user import UserOut, PyObjectId

# Initialize logger
logger = logging.getLogger(__name__)

router = APIRouter()

# Get JWT settings from environment
SECRET_KEY = os.getenv("JWT_SECRET", "change_this_secret")
ALGORITHM = "HS256"

# OAuth2 scheme - must match the one in auth.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decode the JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
            
        # Check token expiration
        exp = payload.get("exp")
        if not exp or datetime.now(timezone.utc).timestamp() > exp:
            raise credentials_exception
            
    except (JWTError, jwt.PyJWTError) as e:
        logger.error(f"JWT Error: {str(e)}")
        raise credentials_exception
    
    # Get user from database using the user_id from the token
    try:
        user = await db["users"].find_one({"_id": ObjectId(user_id)})
    except:
        raise credentials_exception
        
    if user is None:
        raise credentials_exception
        
    # Convert ObjectId to string for JSON serialization
    user["id"] = str(user["_id"])
    return user

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current user's profile information.
    """
    # Convert ObjectId to string for the response
    current_user["id"] = str(current_user["_id"])
    return current_user

@router.get("/{user_id}", response_model=UserOut)
async def read_user(user_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get user by ID (admin only).
    """
    # Check if current user is admin
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    try:
        user = await db["users"].find_one({"_id": ObjectId(user_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
        
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Convert ObjectId to string for the response
    user["id"] = str(user["_id"])
    return user
