from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    storj_bucket = Column(String, unique=True)           # e.g. vibepilot-user-123
    storj_access_grant = Column(String)                  # encrypted grant
    stripe_customer_id = Column(String)
    subscription_tier = Column(String, default="starter") # starter/pro/beast
    founding_rank = Column(Integer, nullable=True)        # locked after 72 hrs
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    def is_founding_member(self):
        return self.founding_rank is not None and self.founding_rank <= 500
