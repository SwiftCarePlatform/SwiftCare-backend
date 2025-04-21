from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
import jwt, os, datetime

from models.user import UserCreate, UserInDB, UserOut
from main import db

router = APIRouter()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = pwd_context.hash(user.password)
    user_in_db = UserInDB(**user.dict(exclude={"password"}), hashed_password=hashed_pw)
    doc = user_in_db.dict(by_alias=True)
    dob = doc.get('dob')
    if isinstance(dob, datetime.date):
        doc['dob'] = datetime.datetime(dob.year, dob.month, dob.day)
    result = await db.users.insert_one(doc)
    created = await db.users.find_one({"_id": result.inserted_id})
    return created

@router.post("/login", response_model=Token)
async def login(login_req: LoginRequest):
    user = await db.users.find_one({"email": login_req.email})
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    user_in_db = UserInDB(**user)
    if not pwd_context.verify(login_req.password, user_in_db.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_in_db.id), "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

    return user
