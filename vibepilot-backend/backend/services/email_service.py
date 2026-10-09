# backend/services/email_service.py
import html as html_lib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables (optionally from a file given by VP_ENV_FILE)
load_dotenv(os.getenv("VP_ENV_FILE") or None)
class EmailService:
    """Send email notifications for reviews"""
    
    def __init__(self):
        # For MVP: Use environment variables
        # Production: Move to proper config
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.from_email = os.getenv("FROM_EMAIL", self.smtp_user)
        
    def send_review_notification(
        self, 
        to_email: str, 
        business_name: str,
        rating: int,
        review_text: Optional[str],
        customer_name: Optional[str],
        job_id: str
    ) -> bool:
        """Send notification when new review is received"""
        
        # Skip if SMTP not configured
        if not self.smtp_host or not self.smtp_user or not self.smtp_pass:
            print("⚠️  Email not configured - skipping notification")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"⭐ New {rating}-Star Review Received!"
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # HTML email body
            stars = "⭐" * rating
            customer_display = html_lib.escape(customer_name or "Anonymous Customer")
            review_display = html_lib.escape(review_text or "(No written review)")
            job_id = html_lib.escape(job_id)
            base_url = html_lib.escape(os.getenv("VP_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"))
            
            html = f"""
            <html>
              <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); padding: 30px; text-align: center;">
                  <h1 style="color: white; margin: 0;">New Verified Review!</h1>
                </div>
                
                <div style="padding: 30px; background: #f9fafb;">
                  <div style="background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px;">
                    <h2 style="color: #1f2937; margin-top: 0;">{stars} {rating} Stars</h2>
                    <p style="color: #6b7280; font-size: 14px; margin: 5px 0;">
                      <strong>From:</strong> {customer_display}
                    </p>
                    <p style="color: #6b7280; font-size: 14px; margin: 5px 0;">
                      <strong>Job:</strong> {job_id}
                    </p>
                    <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin-top: 15px;">
                      <p style="color: #374151; margin: 0; font-style: italic;">"{review_display}"</p>
                    </div>
                  </div>
                  
                  <div style="background: #dcfce7; border: 2px solid #22c55e; border-radius: 10px; padding: 15px; text-align: center;">
                    <p style="color: #166534; margin: 0; font-weight: bold;">✓ Cryptographically Verified</p>
                    <p style="color: #15803d; margin: 5px 0; font-size: 14px;">This review cannot be faked or spoofed</p>
                  </div>
                  
                  <div style="text-align: center; margin-top: 30px;">
                    <a href="{base_url}/dashboard/settings" 
                       style="background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                      View All Reviews
                    </a>
                  </div>
                </div>
                
                <div style="text-align: center; padding: 20px; color: #6b7280; font-size: 12px;">
                  <p>Powered by 🟣 VibePilot</p>
                </div>
              </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            print("✅ Review email notification sent")
            return True
            
        except Exception as e:
            print(f"❌ Email failed: {type(e).__name__}")
            return False
