-- VibePilot Posts & Analytics Schema
-- Compatible with existing BIGINT tenant/user IDs

-- ============================================================================
-- POSTS: Migrated from post_queue/*.json
-- ============================================================================
CREATE TABLE IF NOT EXISTS posts (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  
  caption TEXT NOT NULL,
  image_path TEXT,
  image_prompt TEXT,
  category TEXT,
  status TEXT NOT NULL DEFAULT 'pending_review',
  platform TEXT,
  scheduled_for TIMESTAMPTZ,
  posted_at TIMESTAMPTZ,
  caption_voice_score INTEGER,
  image_accuracy_score INTEGER,
  rating INTEGER,
  performance_score DECIMAL,
  used_llm BOOLEAN DEFAULT false,
  training_example BOOLEAN DEFAULT false,
  caption_hash TEXT,
  legacy_filename TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_posts_tenant ON posts(tenant_id);
CREATE INDEX idx_posts_status ON posts(status);
CREATE INDEX idx_posts_category ON posts(category);

CREATE TABLE IF NOT EXISTS qr_codes (
  id BIGSERIAL PRIMARY KEY,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  token TEXT UNIQUE NOT NULL,
  business_name TEXT,
  job_id TEXT,
  scans INTEGER DEFAULT 0,
  reviews_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
  id BIGSERIAL PRIMARY KEY,
  qr_code_id BIGINT NOT NULL REFERENCES qr_codes(id) ON DELETE CASCADE,
  tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
  review_text TEXT,
  customer_name TEXT,
  verified BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER update_posts_updated_at BEFORE UPDATE ON posts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
