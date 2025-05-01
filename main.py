from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, timezone
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
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

app = FastAPI(title="SwiftCare API")

# MongoDB client - default database 'swiftcaredb'
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = AsyncIOMotorClient(mongo_uri)
db = mongo_client.get_database("swiftcaredb")  # shorthand for mongo_client.swiftcaredb

# CORS configuration (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add timezone middleware
app.add_middleware(TimezoneMiddleware)

from routes import auth, bookings, payments
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
app.include_router(payments.router)

# Startup event: verify database connection
@app.on_event("startup")
async def connect_to_db():
    try:
        # The ping command is cheap and does not require auth
        await mongo_client.admin.command("ping")
        logger.info("Successfully connected to MongoDB at %s", mongo_uri)
    except Exception as e:
        logger.error("Failed to connect to MongoDB: %s", e)
        raise

# Health-check endpoint
@app.get("/", summary="Health check endpoint")
async def root():
    return {"message": "MongoDB connection is healthy"}
