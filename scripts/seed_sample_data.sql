-- Sample Data for Development/Testing
-- ════════════════════════════════════════════════════════════════════════
-- This script inserts realistic sample data for local development.
-- DO NOT run this in production.
--
-- Prerequisites:
--   - All migrations applied (migrations/001-016)
--   - Existing auth users with profiles (created via signup)
--
-- Usage:
--   Run manually in Supabase SQL Editor (development only)
--   Or via Supabase MCP tool: supabase_execute_sql
-- ════════════════════════════════════════════════════════════════════════

-- ────────────────────────────────────────────────────────────────────────
-- EXISTING PROFILES (from auth.users)
-- ────────────────────────────────────────────────────────────────────────
-- Profile 1: 0fa49b04-db80-45a3-ba82-1f623df74e95 (business, kolably.cafe@gmail.com)
-- Profile 2: 4417a424-386b-4fae-8d98-36e5787359bd (creator, kolablyofficial@gmail.com)
-- Business:  75574dd2-5f1c-4ae7-8e11-e56e9b706da7 (linked to profile 1)

-- ────────────────────────────────────────────────────────────────────────
-- 1. CREATORS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO creators (id, profile_id, name, username, bio, instagram_handle, follower_count, engagement_rate, profile_photo_url, city, niche, youtube_handle, tiktok_handle)
VALUES
  ('c1111111-1111-1111-1111-111111111111', '4417a424-386b-4fae-8d98-36e5787359bd',
   'Priya Sharma', 'priya.eats',
   'Food blogger exploring Delhi street food. 5+ years of content creation.',
   '@priya.eats', 45000, 4.8,
   'https://example.com/photos/priya.jpg', 'Delhi', 'food',
   '@priyasharma', '@priya.eats')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 2. BUSINESSES (update existing)
-- ────────────────────────────────────────────────────────────────────────
UPDATE businesses SET
  business_name = 'Kolably Cafe',
  owner_name = 'Amit Kumar',
  category = 'Cafe',
  description = 'New cafe in Connaught Place serving artisan coffee and fresh pastries.',
  website = 'https://kolablycafe.com',
  instagram_handle = '@kolablycafe',
  city = 'Delhi',
  address = '123 Connaught Place, New Delhi',
  logo_url = 'https://example.com/logos/kolably.png',
  industry = 'food_and_beverage',
  is_verified = true
WHERE id = '75574dd2-5f1c-4ae7-8e11-e56e9b706da7';

-- ────────────────────────────────────────────────────────────────────────
-- 3. CAMPAIGNS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO campaigns (id, business_id, title, objective, description, deliverables, compensation_type, cash_amount_min, cash_amount_max, free_product_description, creator_category, follower_range_min, follower_range_max, min_engagement_rate, location, max_creators, additional_requirements, cover_image_url, deadline, status)
VALUES
  ('cafe1111-1111-1111-1111-111111111111', '75574dd2-5f1c-4ae7-8e11-e56e9b706da7',
   'Cafe Launch Collaboration', 'foot_traffic',
   'Help us promote our new cafe opening in Delhi! We need authentic food content creators.',
   '[{"platform": "instagram", "content_type": "reel", "quantity": 1, "description": "Cafe tour reel", "required": true}, {"platform": "instagram", "content_type": "story", "quantity": 3, "description": "Food stories", "required": true}]'::jsonb,
   'cash_and_product', 3000, 5000, 'Free meal for two people',
   'food', 10000, 100000, 3.0, 'Delhi', 5,
   'Must visit cafe in person. Content should highlight ambiance and food quality.',
   'https://example.com/covers/cafe-launch.jpg', '2026-09-30T23:59:59Z', 'active'),

  ('cafe2222-2222-2222-2222-222222222222', '75574dd2-5f1c-4ae7-8e11-e56e9b706da7',
   'Fitness Workshop Promotion', 'event_promotion',
   'Promote our upcoming fitness workshop in Mumbai.',
   '[{"platform": "instagram", "content_type": "post", "quantity": 2, "required": true}]'::jsonb,
   'cash', 2000, 4000, NULL,
   'fitness', 20000, 150000, 4.0, 'Mumbai', 3,
   'Must have fitness certification or proven fitness content experience.',
   NULL, '2026-10-15T23:59:59Z', 'draft'),

  ('cafe3333-3333-3333-3333-333333333333', '75574dd2-5f1c-4ae7-8e11-e56e9b706da7',
   'Summer Menu Launch', 'product_launch',
   'Launch our new summer menu with refreshing drinks and desserts.',
   '[{"platform": "instagram", "content_type": "reel", "quantity": 1, "required": true}, {"platform": "youtube", "content_type": "video", "quantity": 1, "required": false}]'::jsonb,
   'cash_and_product', 4000, 6000, 'Free summer menu tasting',
   'food', 15000, 80000, 3.5, 'Delhi', 4,
   NULL,
   'https://example.com/covers/summer-menu.jpg', '2026-06-30T23:59:59Z', 'completed')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 4. CAMPAIGN APPLICATIONS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO campaign_applications (id, campaign_id, creator_id, direction, message, instagram_handle, example_content_url, status, revision_reason)
VALUES
  ('a1000001-1111-1111-1111-111111111111', 'cafe1111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111',
   'creator_applied', 'Hi! I love your cafe concept. I have 45K followers in food niche and 4.8% engagement. Would love to collaborate!',
   '@priya.eats', 'https://instagram.com/reel/example1', 'accepted', NULL),

  ('a1000003-3333-3333-3333-333333333333', 'cafe3333-3333-3333-3333-333333333333', 'c1111111-1111-1111-1111-111111111111',
   'creator_applied', 'Excited about the summer menu! I create great food content.',
   '@priya.eats', 'https://instagram.com/reel/example2', 'accepted', NULL)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 5. COLLABORATIONS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO collaborations (id, application_id, campaign_id, creator_id, business_id, status, affiliate_url, completed_at)
VALUES
  ('c0000001-1111-1111-1111-111111111111', 'a1000001-1111-1111-1111-111111111111',
   'cafe1111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111', '75574dd2-5f1c-4ae7-8e11-e56e9b706da7',
   'active', NULL, NULL),

  ('c0000002-2222-2222-2222-222222222222', 'a1000003-3333-3333-3333-333333333333',
   'cafe3333-3333-3333-3333-333333333333', 'c1111111-1111-1111-1111-111111111111', '75574dd2-5f1c-4ae7-8e11-e56e9b706da7',
   'completed', NULL, '2026-07-15T10:00:00Z')
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 6. CONTENT SUBMISSIONS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO content_submissions (id, collaboration_id, content_url, platform, views, likes, comments, notes, synced_at)
VALUES
  ('5b000001-1111-1111-1111-111111111111', 'c0000002-2222-2222-2222-222222222222',
   'https://instagram.com/reel/summer-menu-reel', 'instagram',
   52000, 4200, 380, 'Great engagement on this reel! Lots of positive comments.', '2026-07-10T14:30:00Z'),

  ('5b000002-2222-2222-2222-222222222222', 'c0000002-2222-2222-2222-222222222222',
   'https://youtube.com/watch?v=summer-menu-video', 'youtube',
   8500, 620, 45, 'YouTube review of summer menu items.', NULL)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 7. PORTFOLIO ITEMS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO portfolio_items (id, creator_id, media_url, post_link, media_type, like_count, comment_count)
VALUES
  ('d0000001-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111',
   'https://example.com/portfolio/priya-reel1.mp4', 'https://instagram.com/reel/example1', 'video', 3800, 220),
  ('d0000002-2222-2222-2222-222222222222', 'c1111111-1111-1111-1111-111111111111',
   'https://example.com/portfolio/priya-photo1.jpg', 'https://instagram.com/p/example2', 'photo', 2100, 85)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 8. SAVED CAMPAIGNS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO saved_campaigns (creator_id, campaign_id)
VALUES
  ('c1111111-1111-1111-1111-111111111111', 'cafe2222-2222-2222-2222-222222222222')
ON CONFLICT (creator_id, campaign_id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 9. CONVERSATIONS & MESSAGES
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO conversations (id, collaboration_id)
VALUES
  ('e0000001-1111-1111-1111-111111111111', 'c0000001-1111-1111-1111-111111111111')
ON CONFLICT (id) DO NOTHING;

INSERT INTO conversation_participants (conversation_id, profile_id)
VALUES
  ('e0000001-1111-1111-1111-111111111111', '4417a424-386b-4fae-8d98-36e5787359bd'),
  ('e0000001-1111-1111-1111-111111111111', '0fa49b04-db80-45a3-ba82-1f623df74e95')
ON CONFLICT (conversation_id, profile_id) DO NOTHING;

INSERT INTO messages (id, conversation_id, sender_id, content)
VALUES
  ('f1000001-1111-1111-1111-111111111111', 'e0000001-1111-1111-1111-111111111111', '0fa49b04-db80-45a3-ba82-1f623df74e95',
   'Hi Priya! Thanks for joining our cafe launch campaign. When can you visit?'),
  ('f1000002-2222-2222-2222-222222222222', 'e0000001-1111-1111-1111-111111111111', '4417a424-386b-4fae-8d98-36e5787359bd',
   'Hi! I can visit this weekend. Saturday afternoon works best for me.'),
  ('f1000003-3333-3333-3333-333333333333', 'e0000001-1111-1111-1111-111111111111', '0fa49b04-db80-45a3-ba82-1f623df74e95',
   'Perfect! Saturday 2 PM works. I will have a table reserved for you. Looking forward to it!')
ON CONFLICT (id) DO NOTHING;

INSERT INTO conversation_reads (conversation_id, profile_id, last_read_at)
VALUES
  ('e0000001-1111-1111-1111-111111111111', '4417a424-386b-4fae-8d98-36e5787359bd', NOW()),
  ('e0000001-1111-1111-1111-111111111111', '0fa49b04-db80-45a3-ba82-1f623df74e95', NOW())
ON CONFLICT (conversation_id, profile_id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- 10. NOTIFICATIONS
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO notifications (id, profile_id, type, title, body, related_id, is_read)
VALUES
  ('b1000001-1111-1111-1111-111111111111', '0fa49b04-db80-45a3-ba82-1f623df74e95',
   'application_received', 'New Application Received',
   'Priya Sharma applied to your Cafe Launch Collaboration campaign.',
   'a1000001-1111-1111-1111-111111111111', true),

  ('b1000002-2222-2222-2222-222222222222', '4417a424-386b-4fae-8d98-36e5787359bd',
   'application_accepted', 'Application Accepted!',
   'Your application to Cafe Launch Collaboration has been accepted. Check your collaborations.',
   'c0000001-1111-1111-1111-111111111111', true),

  ('b1000003-3333-3333-3333-333333333333', '4417a424-386b-4fae-8d98-36e5787359bd',
   'new_message', 'New Message',
   'Kolably Cafe sent you a message in your conversation.',
   'e0000001-1111-1111-1111-111111111111', false)
ON CONFLICT (id) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Summary
-- ────────────────────────────────────────────────────────────────────────
-- Created (using existing profiles):
--   - 1 creator (Priya Sharma, food niche, 45K followers)
--   - 1 business updated (Kolably Cafe, verified)
--   - 3 campaigns (1 active, 1 draft, 1 completed)
--   - 2 campaign applications (both accepted)
--   - 2 collaborations (1 active, 1 completed)
--   - 2 content submissions with metrics
--   - 2 portfolio items
--   - 1 saved campaign
--   - 1 conversation with 3 messages
--   - 3 notifications (2 read, 1 unread)
-- ════════════════════════════════════════════════════════════════════════
