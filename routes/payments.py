from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from models.payment import PaymentCreate, PaymentResponse, PaymentDB
from services.payment_service import PaymentService
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import logging
from routes.auth import get_current_user

# Get database instance
from main import db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])

def get_payment_service():
    return PaymentService(db)

@router.post("/payments/initialize", response_model=PaymentResponse)
async def initialize_payment(
    payment: PaymentCreate,
    current_user: dict = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Initialize a new payment transaction.
    
    - Requires authentication
    - Creates a new payment record
    - Returns payment details with authorization URL
    """
    try:
        # Set email from authenticated user if not provided
        if not payment.email:
            payment.email = current_user["email"]
            
        payment_db = await payment_service.create_payment(payment)
        return payment_db
    except Exception as e:
        logger.error(f"Payment initialization failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Payment initialization failed: {str(e)}"
        )

@router.get("/payments/verify/{reference}", response_model=PaymentResponse)
async def verify_payment(
    reference: str,
    payment_service: PaymentService = Depends(get_payment_service),
    current_user: dict = Depends(get_current_user)
):
    """
    Verify a payment transaction.
    
    - Requires authentication
    - Verifies payment status with Paystack
    - Updates payment record in database
    """
    try:
        # First check if payment exists and belongs to user
        payment = await payment_service.get_payment(reference)
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")
        
        if payment.email != current_user["email"]:
            raise HTTPException(status_code=403, detail="Not authorized to verify this payment")
            
        verified_payment = await payment_service.verify_payment(reference)
        return verified_payment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payment verification failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Payment verification failed: {str(e)}"
        )

@router.get("/payments", response_model=List[PaymentResponse])
async def get_payment_history(
    status: str = Query(None, description="Filter by payment status"),
    current_user: dict = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service)
):
    """
    Get payment history for the authenticated user.
    
    - Requires authentication
    - Optional status filter
    - Returns list of payments
    """
    try:
        payments = await payment_service.get_user_payments(current_user["email"])
        
        # Filter by status if provided
        if status:
            payments = [p for p in payments if p.status == status]
            
        return payments
    except Exception as e:
        logger.error(f"Failed to fetch payment history: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch payment history: {str(e)}"
        )
