import httpx
from fastapi import HTTPException
import os
from typing import Optional
import uuid
from datetime import datetime
from models.payment import PaymentCreate, PaymentDB, PaymentStatus
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self, db: AsyncIOMotorClient):
        self.secret_key = os.getenv("PAYSTACK_SECRET_KEY")
        self.base_url = "https://api.paystack.co"
        self.db = db
        if not self.secret_key:
            raise ValueError("PAYSTACK_SECRET_KEY environment variable is not set")

    async def _make_request(self, method: str, endpoint: str, json=None) -> dict:
        """Make HTTP request to Paystack API"""
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}/{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method,
                    url,
                    json=json,
                    headers=headers
                )
                response.raise_for_status()
                return response.json()["data"]
            except httpx.HTTPError as e:
                logger.error(f"Paystack API error: {str(e)}")
                raise HTTPException(status_code=400, detail=str(e))

    async def create_payment(self, payment: PaymentCreate) -> PaymentDB:
        """Initialize a payment transaction"""
        # Generate reference if not provided
        if not payment.reference:
            payment.reference = f"TX-{uuid.uuid4().hex[:16]}"

        # Prepare payload for Paystack
        payload = {
            "amount": int(payment.amount * 100),  # Convert to kobo
            "email": payment.email,
            "reference": payment.reference,
            "currency": payment.currency,
            "metadata": {
                "booking_id": payment.booking_id,
                "description": payment.description
            }
        }

        # Initialize transaction with Paystack
        data = await self._make_request("POST", "transaction/initialize", payload)
        
        # Create payment record
        payment_db = PaymentDB(
            **payment.dict(),
            reference=data["reference"],
            authorization_url=data["authorization_url"],
            access_code=data["access_code"]
        )

        # Save to database
        await self.db.swiftcaredb.payments.insert_one(payment_db.dict(by_alias=True))
        
        return payment_db

    async def verify_payment(self, reference: str) -> PaymentDB:
        """Verify a payment transaction"""
        data = await self._make_request("GET", f"transaction/verify/{reference}")
        
        # Update payment status in database
        update_data = {
            "status": PaymentStatus.SUCCESS if data["status"] == "success" else PaymentStatus.FAILED,
            "paid_at": datetime.utcnow() if data["status"] == "success" else None,
            "updated_at": datetime.utcnow()
        }

        result = await self.db.swiftcaredb.payments.find_one_and_update(
            {"reference": reference},
            {"$set": update_data},
            return_document=True
        )

        if not result:
            raise HTTPException(status_code=404, detail="Payment not found")

        return PaymentDB(**result)

    async def get_payment(self, reference: str) -> Optional[PaymentDB]:
        """Get payment by reference"""
        result = await self.db.swiftcaredb.payments.find_one({"reference": reference})
        if not result:
            return None
        return PaymentDB(**result)

    async def get_user_payments(self, email: str) -> list[PaymentDB]:
        """Get all payments for a user"""
        cursor = self.db.swiftcaredb.payments.find({"email": email})
        payments = await cursor.to_list(length=None)
        return [PaymentDB(**payment) for payment in payments]
