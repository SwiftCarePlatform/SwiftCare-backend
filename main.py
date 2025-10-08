from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, timezone
from pydantic import BaseModel

# Load environment variables from .env
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom middleware to convert datetime objects to timezone-aware
class TimezoneMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def receive_with_timezone():
            message = await receive()
            if message["type"] == "http.request":
                # Process here if needed
                pass
            return message

        return await self.app(scope, receive_with_timezone, send)

# Import database module - this should be used by all routes
from database import db, test_connection

app = FastAPI(title="SwiftCare API")

# CORS configuration (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timezone middleware
app.add_middleware(TimezoneMiddleware)

# Health-check endpoint
@app.get("/", summary="Health check endpoint")
async def root():
    return {"message": "API is running"}

# Startup event: verify database connection
@app.on_event("startup")
async def connect_to_db():
    await test_connection()

# Import and include routers
from routes import auth, bookings, doctors, users
# Commenting out payments to isolate payment features
# from routes import payments
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(doctors.router)
# app.include_router(payments.router)

# Add this block to run the app directly with python3 main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
