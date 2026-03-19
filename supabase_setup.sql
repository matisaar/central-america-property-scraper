-- Supabase Likes Table Setup
-- Run this in your Supabase SQL Editor (https://app.supabase.com)

CREATE TABLE likes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  property_id INTEGER NOT NULL,
  ip_address TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(property_id, ip_address)
);

-- Enable Row Level Security
ALTER TABLE likes ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read likes
CREATE POLICY "Anyone can read likes" ON likes FOR SELECT USING (true);

-- Allow anyone to insert likes (one per IP per property via unique constraint)
CREATE POLICY "Anyone can insert likes" ON likes FOR INSERT WITH CHECK (true);

-- Allow anyone to delete their own likes
CREATE POLICY "Anyone can delete likes" ON likes FOR DELETE USING (true);

-- Index for fast lookups
CREATE INDEX idx_likes_property ON likes(property_id);
CREATE INDEX idx_likes_ip ON likes(ip_address);
