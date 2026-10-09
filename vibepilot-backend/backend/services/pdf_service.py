# backend/services/pdf_service.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from io import BytesIO
import base64

class PDFService:
    """Generate printable PDFs for QR codes"""
    
    def create_sticker_sheet(self, qr_code_base64: str, business_name: str) -> bytes:
        """
        Create 8-up sticker sheet (2 columns x 4 rows)
        Standard Avery 5164 size: 4" x 3.33"
        """
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1*inch, height - 0.5*inch, f"{business_name} - QR Review Codes")
        
        # Decode QR image once
        qr_img_data = base64.b64decode(qr_code_base64)
        
        # 8 stickers: 2 columns x 4 rows
        sticker_width = 4 * inch
        sticker_height = 3.33 * inch
        margin_x = 0.25 * inch
        margin_y = 0.5 * inch
        start_y = height - 1.5 * inch
        
        for row in range(4):
            for col in range(2):
                x = margin_x + (col * (sticker_width + 0.2*inch))
                y = start_y - (row * (sticker_height + 0.2*inch))
                
                # Draw border
                c.setStrokeColorRGB(0.5, 0.5, 0.5)
                c.setLineWidth(0.5)
                c.rect(x, y - sticker_height, sticker_width, sticker_height)
                
                # Draw QR code - Create new BytesIO for each image
                qr_buffer = BytesIO(qr_img_data)
                qr_image = ImageReader(qr_buffer)
                
                qr_size = 2 * inch
                qr_x = x + (sticker_width - qr_size) / 2
                qr_y = y - sticker_height + 0.8 * inch
                
                c.drawImage(qr_image, qr_x, qr_y, qr_size, qr_size)
                
                # Add text
                c.setFont("Helvetica-Bold", 12)
                text_y = y - sticker_height + 0.4*inch
                c.drawCentredString(x + sticker_width/2, text_y, "Scan for Verified Review")
                
                c.setFont("Helvetica", 9)
                c.drawCentredString(x + sticker_width/2, text_y - 0.2*inch, "Get 10% Off Next Service!")
        
        # Footer
        c.setFont("Helvetica", 8)
        c.drawCentredString(width/2, 0.3*inch, "Powered by VibePilot")
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
