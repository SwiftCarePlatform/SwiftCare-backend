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
        self.emailjs_user_id = os.getenv("EMAILJS_USER_ID")
        self.emailjs_service_id = os.getenv("EMAILJS_SERVICE_ID")
        self.emailjs_private_key = os.getenv("EMAILJS_PRIVATE_KEY")
        self.welcome_template_id = os.getenv("EMAILJS_WELCOME_TEMPLATE")
        self.booking_template_id = os.getenv("EMAILJS_BOOKING_TEMPLATE")
        self.api_url = "https://api.emailjs.com/api/v1.0/email/send"
        
        # Check for required configurations
        if not self.emailjs_private_key:
            logger.warning("EMAILJS_PRIVATE_KEY environment variable is not set. Email sending will be simulated.")
        if not self.emailjs_user_id:
            logger.warning("EMAILJS_USER_ID environment variable is not set. Email sending will be simulated.")
        if not self.emailjs_service_id:
            logger.warning("EMAILJS_SERVICE_ID environment variable is not set. Email sending will be simulated.")

    async def send_email(
        self,
        template_id: str,
        template_params: Dict,
        to_email: str
    ) -> bool:
        # Check if email configuration is complete
        if not (self.emailjs_user_id and self.emailjs_service_id and template_id):
            logger.info(f"[SIMULATED EMAIL] Template: {template_id}, To: {to_email}, Params: {template_params}")
            return True  # Pretend success in development environment
            
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

                headers = {
                    "Content-Type": "application/json"
                }
                
                if self.emailjs_private_key:
                    payload["accessToken"] = self.emailjs_private_key
                    headers["Authorization"] = f"Bearer {self.emailjs_private_key}"

                async with session.post(self.api_url, json=payload, headers=headers) as response:
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

    async def send_welcome_email(self, user_email: str, first_name: str, last_name: str = ""):
        template_params = {
            "first_name": first_name,
            "full_name": f"{first_name} {last_name}".strip(),
            "email": user_email
        }
        
        # Use default template ID if not configured
        template_id = self.welcome_template_id or "welcome_template"
        
        await self.send_email(
            template_id=template_id,
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
        
        # Use default template ID if not configured
        template_id = self.booking_template_id or "booking_template"
        
        await self.send_email(
            template_id=template_id,
            template_params=template_params,
            to_email=user_email
        )

# Create a singleton instance
email_service = EmailService()
