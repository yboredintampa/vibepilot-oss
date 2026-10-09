# backend/services/qr_service.py
import hashlib
import hmac
import re
import secrets

import qrcode
from datetime import datetime
from io import BytesIO
import base64
from typing import Dict, Optional

from backend.security import public_base_url, require_env

_TOKEN_PART = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")

class QRReputationService:
    """
    Generate QR codes for verified review collection
    Each QR contains a unique token tied to a specific job/user
    """
    
    def __init__(self):
        # Signing key must come from the environment; there is no default.
        self.secret_key = require_env("QR_SIGNING_SECRET").encode("utf-8")

    def _sign(self, payload: str) -> str:
        return hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    
    def generate_qr_token(self, user_id: str, job_id: Optional[str] = None) -> str:
        """
        Generate a unique, cryptographically signed token
        Format: {user_id}:{job_id}:{timestamp}:{signature}
        """
        timestamp = int(datetime.now().timestamp())
        job_id = job_id or secrets.token_hex(8)
        if not _TOKEN_PART.match(user_id) or not _TOKEN_PART.match(job_id):
            raise ValueError("user_id/job_id contain invalid characters")
        
        # Create payload
        payload = f"{user_id}:{job_id}:{timestamp}"
        
        # Generate signature
        signature = self._sign(payload)

        token = f"{payload}:{signature}"
        return token
    
    def verify_token(self, token: str, max_age_days: int = 60) -> Dict:
        """
        Verify token hasn't been tampered with and isn't expired
        Returns user_id, job_id, timestamp if valid
        """
        try:
            parts = token.split(":")
            if len(parts) != 4:
                return {"valid": False, "error": "Invalid token format"}
            
            user_id, job_id, timestamp, signature = parts
            if not (_TOKEN_PART.match(user_id) and _TOKEN_PART.match(job_id) and timestamp.isdigit()):
                return {"valid": False, "error": "Invalid token format"}
            
            # Check expiration (60 days default)
            token_age_days = (datetime.now().timestamp() - int(timestamp)) / 86400
            if token_age_days > max_age_days:
                return {"valid": False, "error": f"Token expired ({int(token_age_days)} days old)"}
            
            # Recreate signature
            payload = f"{user_id}:{job_id}:{timestamp}"
            expected_sig = self._sign(payload)

            if not hmac.compare_digest(signature, expected_sig):
                return {"valid": False, "error": "Invalid signature"}
            
            return {
                "valid": True,
                "user_id": user_id,
                "job_id": job_id,
                "timestamp": int(timestamp),
                "age_days": int(token_age_days)
            }
        except Exception:
            return {"valid": False, "error": "Invalid token"}
    
    def generate_qr_code(self, user_id: str, job_id: Optional[str] = None) -> Dict:
        """
        Generate QR code image for review collection
        Returns base64 encoded PNG
        """
        # Generate token
        token = self.generate_qr_token(user_id, job_id)
        
        # Create review URL
        review_url = f"{public_base_url()}/qr/review/{token}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(review_url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            "token": token,
            "url": review_url,
            "qr_code_base64": img_base64,
            "job_id": token.split(":")[1]
        }
    
    def create_printable_qr(self, user_id: str, business_name: str) -> Dict:
        """
        Generate a master QR code for printing on trucks/invoices
        This QR can be used for multiple jobs
        """
        qr_data = self.generate_qr_code(user_id, job_id="MASTER")
        
        return {
            **qr_data,
            "business_name": business_name,
            "instructions": "Scan to leave a verified review and get 10% off your next service!"
        }
