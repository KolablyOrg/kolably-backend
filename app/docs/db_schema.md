# 1️⃣ Core Database Architecture

Your platform revolves around **four main entities**:

```text
Users
Businesses
Creators
Campaigns
```

Everything else attaches to those.

High-level structure:

```
profiles
   │
   ├── creators
   └── businesses

campaigns
   │
   └── campaign_applications
          │
          └── collaborations
                 │
                 └── content_submissions
```

---

# 2️⃣ Profiles (already in your plan)

This connects Supabase Auth users to your app.

```sql
CREATE TABLE profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_id UUID UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT CHECK (role IN ('creator','business','superadmin')),
  is_active BOOLEAN DEFAULT TRUE,
  last_seen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

`last_seen_at` is written from the authenticated heartbeat endpoint using
server time. A Redis `presence:{profile_id}` key with a 90-second TTL provides
the fast online signal; the timestamp is used for recently-active fallback.

The `inbox_broadcast_new_message` `AFTER INSERT` trigger fans each committed
message out to `inbox:{profile_id}` for every conversation participant.
`is_inbox_realtime_owner()` and the `inbox_owner_can_receive_broadcast` policy
allow only the profile owner to subscribe. The global presence channel has
authenticated SELECT and INSERT policies for `global:online-users`.

---

# 3️⃣ Creators Table

Creator-specific data.

```sql
CREATE TABLE creators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,

  username TEXT,
  bio TEXT,

  instagram_handle TEXT,
  instagram_followers INT,
  instagram_engagement_rate NUMERIC,

  youtube_channel TEXT,
  youtube_subscribers INT,

  city TEXT,
  niche TEXT,

  created_at TIMESTAMPTZ DEFAULT now()
);
```

Important fields:

```text
instagram_handle
followers
engagement_rate
niche
city
```

These power **creator discovery**.

---

# 4️⃣ Businesses Table

```sql
CREATE TABLE businesses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,

  business_name TEXT NOT NULL,
  category TEXT,
  description TEXT,

  website TEXT,
  instagram_handle TEXT,

  city TEXT,

  created_at TIMESTAMPTZ DEFAULT now()
);
```

Examples:

```text
Cafe
Restaurant
Gym
Clothing brand
Salon
```

---

# 5️⃣ Campaigns Table

This is the **core revenue object**.

```sql
CREATE TABLE campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,

  title TEXT NOT NULL,
  description TEXT,

  deliverables TEXT,
  offer_details TEXT,

  cash_payment NUMERIC,
  free_product BOOLEAN DEFAULT FALSE,

  creator_category TEXT,
  min_followers INT,
  max_followers INT,

  city TEXT,

  campaign_status TEXT CHECK (
      campaign_status IN ('draft','active','closed','completed')
  ) DEFAULT 'draft',

  deadline DATE,

  created_at TIMESTAMPTZ DEFAULT now()
);
```

Example campaign:

```
Title: Cafe Launch Collaboration
Offer: Free meal + ₹2000
Deliverable: 1 Reel + 3 Stories
City: Delhi
```

---

# 6️⃣ Campaign Applications

Creators apply to campaigns.

```sql
CREATE TABLE campaign_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
  creator_id UUID REFERENCES creators(id) ON DELETE CASCADE,

  message TEXT,

  application_status TEXT CHECK (
    application_status IN ('pending','accepted','rejected')
  ) DEFAULT 'pending',

  applied_at TIMESTAMPTZ DEFAULT now(),

  UNIQUE(campaign_id, creator_id)
);
```

This prevents creators applying twice.

---

# 7️⃣ Collaborations Table

When a business **accepts an application**, it becomes a collaboration.

```sql
CREATE TABLE collaborations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
  creator_id UUID REFERENCES creators(id) ON DELETE CASCADE,
  business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,

  agreed_payment NUMERIC,

  collaboration_status TEXT CHECK (
    collaboration_status IN (
      'active',
      'content_submitted',
      'approved',
      'completed',
      'cancelled'
    )
  ) DEFAULT 'active',

  started_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);
```

This table represents **actual deals**.

---

# 8️⃣ Content Submissions

Creators submit content links.

```sql
CREATE TABLE content_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  collaboration_id UUID REFERENCES collaborations(id) ON DELETE CASCADE,

  content_url TEXT,
  platform TEXT,

  views INT,
  likes INT,
  comments INT,

  submitted_at TIMESTAMPTZ DEFAULT now()
);
```

Example:

```
content_url: instagram.com/reel/xyz
platform: instagram
views: 45000
likes: 3800
```

---

# 9️⃣ Chat Messages (optional MVP)

If you want in-platform chat.

```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  collaboration_id UUID REFERENCES collaborations(id),

  sender_profile_id UUID REFERENCES profiles(id),

  message TEXT,

  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

# 🔟 Creator Discovery Indexes

These dramatically improve search speed.

```sql
CREATE INDEX idx_creator_city ON creators(city);
CREATE INDEX idx_creator_niche ON creators(niche);
CREATE INDEX idx_creator_followers ON creators(instagram_followers);
```

---

# 1️⃣1️⃣ Campaign Search Index

```sql
CREATE INDEX idx_campaign_city ON campaigns(city);
CREATE INDEX idx_campaign_status ON campaigns(campaign_status);
```

---

# 1️⃣2️⃣ Full Relationship Diagram

```
profiles
   │
   ├── creators
   │
   └── businesses

businesses
   │
   └── campaigns
           │
           └── campaign_applications
                    │
                    └── collaborations
                           │
                           └── content_submissions
```

---

# 1️⃣3️⃣ How CreatorIQ-style platforms expand this

Platforms like:

* CreatorIQ
* Upfluence

add more tables:

```
creator_social_accounts
creator_audience_demographics
creator_content_history
campaign_payments
campaign_tracking_links
creator_affiliate_sales
brand_relationships
ugc_assets
```

But you **do not need these for MVP**.

---

# 1️⃣4️⃣ MVP tables you actually need

Just these **7 tables**:

```text
profiles
creators
businesses
campaigns
campaign_applications
collaborations
content_submissions
```

That’s enough to run a marketplace.

---

# 1️⃣5️⃣ Critical rule for marketplace databases

Never design like this:

```text
user_id
role
creator_id
business_id
```

Instead always do:

```text
profiles → creators
profiles → businesses
```

Because users may later have **multiple roles**.

---

# Final honest advice

Your biggest mistake right now would be:

```text
spending weeks building perfect infrastructure
```

Instead prioritize:

```text
creator onboarding
campaign liquidity
```

Because without creators and businesses interacting, **the database schema doesn’t matter**.
