-- VibePilot Unified Database Schema
-- Consolidates: tenants, posts, analytics, reputation, dedupe

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- CORE: Tenants & Users
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  plan TEXT DEFAULT 'starter', -- starter/pro/beast
  stripe_customer_id TEXT,
  storj_bucket TEXT,
  founding_rank INTEGER, -- Locked after launch
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  role TEXT NOT NULL DEFAULT 'admin', -- admin/user/viewer
  storj_access_grant TEXT, -- Encrypted
  last_active TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================================
-- POSTS: Migrated from post_queue/*.json
-- ============================================================================
CREATE TABLE IF NOT EXISTS posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  
  -- Content
  caption TEXT NOT NULL,
  image_path TEXT,
  image_prompt TEXT,
  category TEXT, -- pools/hvac/plumbing/dog_grooming/electrical
  
  -- Metadata
  status TEXT NOT NULL DEFAULT 'pending_review', -- pending_review/approved/posted/deleted
  platform TEXT, -- facebook/instagram/nextdoor
  
  -- Scheduling
  scheduled_for TIMESTAMPTZ,
  posted_at TIMESTAMPTZ,
  
  -- Quality scores
  caption_voice_score INTEGER, -- 0-100
  image_accuracy_score INTEGER, -- 0-100
  
  -- Analytics
  rating INTEGER, -- 1-5 stars (from admin review)
  performance_score DECIMAL, -- Calculated from engagement
  
  -- AI Learning
  used_llm BOOLEAN DEFAULT false,
  training_example BOOLEAN DEFAULT false, -- High performers used for training
  
  -- Deduplication
  caption_hash TEXT, -- For similarity checking
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_posts_tenant ON posts(tenant_id);
CREATE INDEX idx_posts_status ON posts(status);
CREATE INDEX idx_posts_category ON posts(category);
CREATE INDEX idx_posts_rating ON posts(rating) WHERE rating IS NOT NULL;
CREATE INDEX idx_posts_caption_hash ON posts(caption_hash);

-- ============================================================================
-- DEDUPLICATION: Migrated from dedupe.sqlite
-- ============================================================================
CREATE TABLE IF NOT EXISTS caption_dedupe (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  caption TEXT NOT NULL,
  caption_hash TEXT NOT NULL,
  category TEXT,
  similarity_threshold DECIMAL DEFAULT 0.85,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dedupe_tenant ON caption_dedupe(tenant_id);
CREATE INDEX idx_dedupe_hash ON caption_dedupe(caption_hash);

-- ============================================================================
-- QR REPUTATION SYSTEM
-- ============================================================================
CREATE TABLE IF NOT EXISTS qr_codes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  
  token TEXT UNIQUE NOT NULL, -- Cryptographic token
  business_name TEXT,
  job_id TEXT,
  
  scans INTEGER DEFAULT 0,
  reviews_count INTEGER DEFAULT 0,
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  qr_code_id UUID NOT NULL REFERENCES qr_codes(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  
  -- Review data
  rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
  review_text TEXT,
  customer_name TEXT,
  customer_email TEXT,
  
  -- Verification
  verified BOOLEAN DEFAULT true,
  verification_token TEXT,
  discount_code TEXT, -- e.g., VERIFIED10
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reviews_qr ON reviews(qr_code_id);
CREATE INDEX idx_reviews_tenant ON reviews(tenant_id);
CREATE INDEX idx_reviews_rating ON reviews(rating);

-- ============================================================================
-- AI ANALYTICS & LEARNING
-- ============================================================================
CREATE TABLE IF NOT EXISTS analytics_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  post_id UUID REFERENCES posts(id) ON DELETE SET NULL,
  
  event_type TEXT NOT NULL, -- post_created/post_approved/post_deleted/engagement
  metadata JSONB DEFAULT '{}',
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_tenant ON analytics_events(tenant_id);
CREATE INDEX idx_analytics_type ON analytics_events(event_type);
CREATE INDEX idx_analytics_created ON analytics_events(created_at);

-- ============================================================================
-- OAUTH CONNECTIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider TEXT NOT NULL, -- facebook/instagram/nextdoor
  account_label TEXT,
  oauth_data_json JSONB NOT NULL DEFAULT '{}',
  scopes TEXT[] NOT NULL DEFAULT '{}',
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- TRIGGERS FOR UPDATED_AT
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = NOW();
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_posts_updated_at BEFORE UPDATE ON posts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
