from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from dotenv import load_dotenv

# Load environment variables
# Configure logging
logger = logging.getLogger(__name__)

# Database connection
def get_database():
    """
    Create and return a database connection with proper SSL configuration.
    In production, ensure MONGO_URI includes the correct parameters for SSL.
    Example for MongoDB Atlas: mongodb+srv://username:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority&tls=true
    """
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable is not set")
        
    ssl_ca_certs = os.getenv("SSL_CA_CERTS")  # Path to CA certificate file if needed
    
    ssl_kwargs = {
        "tls": True,
        "tlsInsecure": False,  # Always verify server certificate
        "serverSelectionTimeoutMS": 5000,
    }
    
    if ssl_ca_certs and os.path.exists(ssl_ca_certs):
        ssl_kwargs["tlsCAFile"] = ssl_ca_certs
        
    mongo_client = AsyncIOMotorClient(mongo_uri, **ssl_kwargs)
    return mongo_client.get_database("swiftcaredb")

# Create a singleton database instance
db = get_database()

# Test database connection
async def test_connection():
    """
    Test the database connection with proper SSL configuration.
    """
    try:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI environment variable is not set")
            
        ssl_ca_certs = os.getenv("SSL_CA_CERTS")
        
        ssl_kwargs = {
            "tls": True,
            "tlsInsecure": False,
            "serverSelectionTimeoutMS": 5000,
        }
        
        if ssl_ca_certs and os.path.exists(ssl_ca_certs):
            ssl_kwargs["tlsCAFile"] = ssl_ca_certs
            
        mongo_client = AsyncIOMotorClient(mongo_uri, **ssl_kwargs)
        await mongo_client.admin.command("ping")
        logger.info(" backend up Successfully connected to SwiftCare Database")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        return False 