from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Database connection
def get_database():
    """
    Create and return a database connection.
    """
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    # Add tlsAllowInvalidCertificates=true to bypass certificate verification
    if "mongodb+srv" in mongo_uri and "?" in mongo_uri:
        mongo_uri += "&tlsAllowInvalidCertificates=true"
    elif "mongodb+srv" in mongo_uri:
        mongo_uri += "?tlsAllowInvalidCertificates=true"
        
    mongo_client = AsyncIOMotorClient(
        mongo_uri,
        serverSelectionTimeoutMS=5000,
        tlsAllowInvalidCertificates=True  # Disable SSL certificate verification
    )
    return mongo_client.get_database("swiftcaredb")

# Create a singleton database instance
db = get_database()

# Test database connection
async def test_connection():
    """
    Test the database connection.
    """
    try:
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        # Add tlsAllowInvalidCertificates=true to bypass certificate verification
        if "mongodb+srv" in mongo_uri and "?" in mongo_uri:
            mongo_uri += "&tlsAllowInvalidCertificates=true"
        elif "mongodb+srv" in mongo_uri:
            mongo_uri += "?tlsAllowInvalidCertificates=true"
            
        mongo_client = AsyncIOMotorClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000,
            tlsAllowInvalidCertificates=True  # Disable SSL certificate verification
        )
        await mongo_client.admin.command("ping")
        logger.info("Successfully connected to MongoDB")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        logger.warning("MongoDB functionality may be limited")
        return False 