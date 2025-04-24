from fastapi import BackgroundTasks
from typing import Dict, Optional
import logging
import os
from dotenv import load_dotenv
import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)
load_dotenv()

class EmailService:
    def __init__(self):
        # Load environment variables with defaults
        self.emailjs_user_id = os.getenv("EMAILJS_USER_ID", "UyXYMghIo7-5Eu8nr")
        self.emailjs_service_id = os.getenv("EMAILJS_SERVICE_ID", "service_swiftcare")
        self.welcome_template_id = os.getenv("EMAILJS_WELCOME_TEMPLATE", "template_471tdx8")
        self.booking_template_id = os.getenv("EMAILJS_BOOKING_TEMPLATE", "template_vbk708m")
        self.api_url = "https://api.emailjs.com/api/v1.0/email/send"

    async def send_email(
        self,
        template_id: str,
        template_params: Dict,
        to_email: str
    ) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "user_id": self.emailjs_user_id,
                    "service_id": self.emailjs_service_id,
                    "template_id": template_id,
                    "template_params": {
                        **template_params,
                        "to_email": to_email
                    }
                }

                async with session.post(self.api_url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Email sent successfully to {to_email}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to send email. Status: {response.status}, Error: {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False

    async def send_welcome_email(self, user_email: str, first_name: str):
        template_params = {
            "first_name": first_name,
            "email": user_email
        }
        
        await self.send_email(
            template_id=self.welcome_template_id,
            template_params=template_params,
            to_email=user_email
        )

    async def send_booking_confirmation(
        self,
        user_email: str,
        booking_details: Dict
    ):
        template_params = {
            **booking_details,
            "email": user_email
        }
        
        await self.send_email(
            template_id=self.booking_template_id,
            template_params=template_params,
            to_email=user_email
        )

# Create a singleton instance
email_service = EmailService()
