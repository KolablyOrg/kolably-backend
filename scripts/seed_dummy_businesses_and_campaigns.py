"""Seed dummy businesses and campaigns so the app has real, browsable data
to test against (creator-side discovery/filtering/applying, business-side
campaign management, etc.).

Creates 11 businesses spanning every CAMPAIGN_CATEGORIES niche (food,
fashion, tech, travel, fitness, lifestyle, entertainment, education,
real_estate, automotive, finance), each a real confirmed auth user so you
can log in as any of them, plus ~3 ACTIVE campaigns per business (so they
show up in the creator feed, which only lists status='active' campaigns).

Idempotent: business/campaign IDs are deterministic (uuid5 of a fixed
namespace + slug), and rows are upserted with resolution=ignore-duplicates
on id — safe to re-run, e.g. after tweaking a description.

Prereqs
-------
  - .env configured with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
  - Migrations applied (needs the on_auth_user_created trigger so a
    profiles row appears after each auth user is created)

Usage
-----
  .venv/bin/python scripts/seed_dummy_businesses_and_campaigns.py

Not a pytest file -- manual/dev seeding only. Never run against production.
"""

import sys
import uuid

import httpx

sys.path.insert(0, ".")
from app.core.config import settings  # noqa: E402

# Fixed, arbitrary namespace -- only needs to be stable across runs so the
# same slug always maps to the same UUID (that's what makes re-running this
# script idempotent rather than creating duplicate rows every time).
SEED_NAMESPACE = uuid.UUID("6f2c9b0a-3c9f-4b8e-9b0a-3c9f4b8e9b0a")

BUSINESS_PASSWORD = "TestBiz123!"


def seed_id(kind: str, slug: str) -> str:
    return str(uuid.uuid5(SEED_NAMESPACE, f"kolably-seed:{kind}:{slug}"))


def cover_image(slug: str) -> str:
    return f"https://picsum.photos/seed/{slug}/800/450"


def logo_image(slug: str) -> str:
    return f"https://picsum.photos/seed/{slug}-logo/300/300"


def deliverable(platform: str, content_type: str, quantity: int, description: str | None = None) -> dict:
    return {
        "platform": platform,
        "content_type": content_type,
        "quantity": quantity,
        "description": description,
        "required": True,
    }


# ── helpers (same REST + service-role pattern as docs/seed_superadmin_business.py) ──

def rest_headers(prefer: str | None = None) -> dict:
    h = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def admin_headers() -> dict:
    return {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def find_profile_by_email(client: httpx.Client, email: str) -> dict | None:
    r = client.get(
        f"{settings.SUPABASE_URL}/rest/v1/profiles",
        headers=rest_headers(),
        params={"email": f"eq.{email}", "select": "*"},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def create_auth_user(client: httpx.Client, email: str, password: str, role: str) -> str:
    """Create the auth user with `role` baked into user_metadata, so the
    on_auth_user_created trigger creates the profiles row at the right
    role already. Returns the auth uid."""
    r = client.post(
        f"{settings.SUPABASE_URL}/auth/v1/admin/users",
        headers=admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"role": role},
        },
        timeout=15,
    )
    if r.status_code in (200, 201):
        return r.json()["id"]
    # Already exists -> look it up instead of failing.
    if r.status_code in (400, 422) and "already" in r.text.lower():
        existing = find_profile_by_email(client, email)
        if existing:
            return existing["auth_id"]
    raise RuntimeError(f"create_auth_user failed: {r.status_code} {r.text}")


def upsert(client: httpx.Client, table: str, rows: list[dict], on_conflict: str) -> None:
    r = client.post(
        f"{settings.SUPABASE_URL}/rest/v1/{table}",
        headers=rest_headers(prefer="resolution=ignore-duplicates,return=minimal"),
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=15,
    )
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"upsert into {table} failed: {r.status_code} {r.text}")


def ensure_business_row(client: httpx.Client, business_id: str, profile_id: str, biz: dict) -> None:
    upsert(
        client,
        "businesses",
        [{
            "id": business_id,
            "profile_id": profile_id,
            "business_name": biz["business_name"],
            "owner_name": biz["owner_name"],
            "category": biz["category"],
            "industry": biz["industry"],
            "city": biz["city"],
            "address": biz["address"],
            "description": biz["description"],
            "website": biz["website"],
            "instagram_handle": biz["instagram_handle"],
            "logo_url": logo_image(biz["slug"]),
            "is_verified": True,
        }],
        on_conflict="id",
    )


# ── dummy data: 11 businesses across every campaign niche ───────────────

BUSINESSES = [
    {
        "slug": "beanstreet-cafe",
        "business_name": "Beanstreet Cafe",
        "owner_name": "Ananya Rao",
        "email": "owner@beanstreetcafe.test",
        "category": "Cafe",
        "industry": "Food & Beverage",
        "city": "Delhi",
        "address": "12 Connaught Place, New Delhi",
        "description": "All-day cafe serving specialty coffee, brunch, and comfort food in the heart of Delhi.",
        "website": "https://beanstreetcafe.test",
        "instagram_handle": "@beanstreetcafe",
        "niche": "food",
        "campaigns": [
            dict(title="Monsoon Menu Launch", objective="product_launch",
                 description="Help us launch our new monsoon menu — pakoras, masala chai, and seasonal specials.",
                 compensation_type="cash", cash_min=2500, cash_max=5000,
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "story", 3)],
                 follower_min=5000, follower_max=50000, engagement=2.5, max_creators=6,
                 additional_requirements="Must dine in and film on location.", deadline="2026-09-15T23:59:59Z"),
            dict(title="Weekend Brunch Experience", objective="foot_traffic",
                 description="Bring your followers along for our weekend brunch spread.",
                 compensation_type="cash_and_product", cash_min=1500, cash_max=3000,
                 free_product="Free brunch for two",
                 deliverables=[deliverable("instagram", "post", 1), deliverable("instagram", "reel", 1)],
                 follower_min=3000, follower_max=40000, engagement=2.0, max_creators=8,
                 deadline="2026-10-01T23:59:59Z"),
            dict(title="Coffee Tasting Series", objective="brand_awareness",
                 description="Feature our single-origin coffee tasting flight in your stories.",
                 compensation_type="product", free_product="Free tasting flight + branded merch",
                 deliverables=[deliverable("instagram", "story", 4)],
                 follower_min=2000, follower_max=30000, max_creators=10,
                 deadline="2026-10-20T23:59:59Z"),
        ],
    },
    {
        "slug": "urban-threads",
        "business_name": "Urban Threads",
        "owner_name": "Rhea Kapoor",
        "email": "hello@urbanthreads.test",
        "category": "Fashion Retail",
        "industry": "Fashion & Apparel",
        "city": "Mumbai",
        "address": "45 Linking Road, Bandra West, Mumbai",
        "description": "Contemporary streetwear label blending Indian prints with modern silhouettes.",
        "website": "https://urbanthreads.test",
        "instagram_handle": "@urbanthreads.in",
        "niche": "fashion",
        "campaigns": [
            dict(title="Festive Collection Drop", objective="product_launch",
                 description="Style our new festive collection your way — sarees, co-ords, and fusion wear.",
                 compensation_type="cash_and_product", cash_min=4000, cash_max=9000,
                 free_product="Full festive outfit of choice",
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "post", 2)],
                 follower_min=15000, follower_max=150000, engagement=3.0, max_creators=5,
                 deadline="2026-09-25T23:59:59Z"),
            dict(title="Everyday Basics Campaign", objective="sales_conversion",
                 description="Show how you style our basics tees and joggers for daily wear.",
                 compensation_type="cash", cash_min=2000, cash_max=4000,
                 deliverables=[deliverable("instagram", "reel", 2)],
                 follower_min=8000, follower_max=80000, max_creators=10,
                 deadline="2026-10-10T23:59:59Z"),
            dict(title="Sustainable Fabric Story", objective="brand_awareness",
                 description="Tell the story of our organic cotton sourcing and dyeing process.",
                 compensation_type="product", free_product="Capsule wardrobe set",
                 deliverables=[deliverable("instagram", "post", 1), deliverable("instagram", "story", 3)],
                 follower_min=10000, follower_max=100000, max_creators=4,
                 deadline="2026-11-05T23:59:59Z"),
        ],
    },
    {
        "slug": "novatech-gadgets",
        "business_name": "NovaTech Gadgets",
        "owner_name": "Karthik Iyer",
        "email": "press@novatechgadgets.test",
        "category": "Consumer Electronics",
        "industry": "Technology",
        "city": "Bengaluru",
        "address": "221 Indiranagar 100 Feet Road, Bengaluru",
        "description": "D2C electronics brand making affordable smart gadgets and audio accessories.",
        "website": "https://novatechgadgets.test",
        "instagram_handle": "@novatech.in",
        "niche": "tech",
        "campaigns": [
            dict(title="TWS Earbuds Launch Review", objective="product_launch",
                 description="Unbox and review our new noise-cancelling earbuds before launch day.",
                 compensation_type="cash_and_product", cash_min=5000, cash_max=12000,
                 free_product="Earbuds + power bank",
                 deliverables=[deliverable("youtube", "video", 1), deliverable("instagram", "reel", 1)],
                 follower_min=20000, follower_max=300000, engagement=2.5, max_creators=6,
                 deadline="2026-09-20T23:59:59Z"),
            dict(title="Smart Home Starter Kit", objective="user_generated_content",
                 description="Set up and showcase our smart plug + bulb starter kit in your home.",
                 compensation_type="cash", cash_min=3000, cash_max=7000,
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "story", 2)],
                 follower_min=10000, follower_max=150000, max_creators=8,
                 deadline="2026-10-15T23:59:59Z"),
            dict(title="Budget Laptop Stand Comparison", objective="brand_awareness",
                 description="Compare our aluminium laptop stand against 2 competitors.",
                 compensation_type="product", free_product="Laptop stand + wireless mouse",
                 deliverables=[deliverable("youtube", "short", 1)],
                 follower_min=5000, follower_max=100000, max_creators=12,
                 deadline="2026-11-01T23:59:59Z"),
        ],
    },
    {
        "slug": "wanderly-travels",
        "business_name": "Wanderly Travels",
        "owner_name": "Meera Nair",
        "email": "partnerships@wanderlytravels.test",
        "category": "Travel Agency",
        "industry": "Travel & Tourism",
        "city": "Panaji",
        "address": "Fisherman's Wharf Road, Panaji, Goa",
        "description": "Curated group trips and villa stays across Goa, Himachal, and the Northeast.",
        "website": "https://wanderlytravels.test",
        "instagram_handle": "@wanderly.travels",
        "niche": "travel",
        "campaigns": [
            dict(title="Goa Beach Villa Getaway", objective="brand_awareness",
                 description="Document a 3-day stay at our beachfront villa in North Goa.",
                 compensation_type="cash_and_product", cash_min=6000, cash_max=15000,
                 free_product="3N/4D villa stay for two",
                 deliverables=[deliverable("instagram", "reel", 2), deliverable("instagram", "story", 5)],
                 follower_min=20000, follower_max=200000, engagement=3.0, max_creators=4,
                 deadline="2026-10-05T23:59:59Z"),
            dict(title="Himalayan Roadtrip Series", objective="event_promotion",
                 description="Join our guided Spiti Valley roadtrip and vlog the journey.",
                 compensation_type="product", free_product="Fully sponsored 6-day roadtrip seat",
                 deliverables=[deliverable("youtube", "video", 1)],
                 follower_min=15000, follower_max=250000, max_creators=3,
                 deadline="2026-11-20T23:59:59Z"),
            dict(title="Weekend Getaway Packages", objective="sales_conversion",
                 description="Promote our new weekend getaway packages near Mumbai and Pune.",
                 compensation_type="cash", cash_min=2500, cash_max=5000,
                 deliverables=[deliverable("instagram", "reel", 1)],
                 follower_min=8000, follower_max=80000, max_creators=10,
                 deadline="2026-09-30T23:59:59Z"),
        ],
    },
    {
        "slug": "fitcore-studio",
        "business_name": "FitCore Studio",
        "owner_name": "Rohan Deshmukh",
        "email": "collabs@fitcorestudio.test",
        "category": "Fitness & Wellness",
        "industry": "Health & Fitness",
        "city": "Pune",
        "address": "Baner Road, Pune",
        "description": "Boutique strength & conditioning studio offering personal training and group HIIT classes.",
        "website": "https://fitcorestudio.test",
        "instagram_handle": "@fitcore.studio",
        "niche": "fitness",
        "campaigns": [
            dict(title="30-Day Transformation Challenge", objective="user_generated_content",
                 description="Join our 30-day strength challenge and document your progress.",
                 compensation_type="cash_and_product", cash_min=4000, cash_max=8000,
                 free_product="1-month free membership",
                 deliverables=[deliverable("instagram", "reel", 4)],
                 follower_min=10000, follower_max=100000, engagement=3.5, max_creators=5,
                 deadline="2026-09-28T23:59:59Z"),
            dict(title="HIIT Class Takeover", objective="brand_awareness",
                 description="Attend and film a live HIIT class session at our studio.",
                 compensation_type="product", free_product="3 free class passes",
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "story", 3)],
                 follower_min=5000, follower_max=60000, max_creators=8,
                 deadline="2026-10-25T23:59:59Z"),
            dict(title="Protein Meal Prep Partnership", objective="product_launch",
                 description="Feature our new in-house meal prep menu for gym-goers.",
                 compensation_type="cash", cash_min=2000, cash_max=4500,
                 deliverables=[deliverable("instagram", "post", 1), deliverable("instagram", "story", 2)],
                 follower_min=6000, follower_max=70000, max_creators=6,
                 deadline="2026-11-10T23:59:59Z"),
        ],
    },
    {
        "slug": "glowroot-living",
        "business_name": "GlowRoot Living",
        "owner_name": "Ishita Bansal",
        "email": "collab@glowrootliving.test",
        "category": "Home & Lifestyle",
        "industry": "Home & Lifestyle",
        "city": "Hyderabad",
        "address": "Jubilee Hills, Hyderabad",
        "description": "Sustainable home decor and lifestyle brand — candles, planters, and handcrafted decor.",
        "website": "https://glowrootliving.test",
        "instagram_handle": "@glowroot.living",
        "niche": "lifestyle",
        "campaigns": [
            dict(title="Room Makeover Reveal", objective="user_generated_content",
                 description="Style a corner of your home with our decor pieces and share the reveal.",
                 compensation_type="product", free_product="Decor bundle worth ₹6000",
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "post", 1)],
                 follower_min=8000, follower_max=90000, max_creators=6,
                 deadline="2026-10-08T23:59:59Z"),
            dict(title="Festive Home Styling", objective="brand_awareness",
                 description="Show how you decorate your home for the festive season with our pieces.",
                 compensation_type="cash_and_product", cash_min=2000, cash_max=4000,
                 free_product="Festive decor hamper",
                 deliverables=[deliverable("instagram", "story", 4)],
                 follower_min=5000, follower_max=70000, max_creators=8,
                 deadline="2026-10-22T23:59:59Z"),
            dict(title="Candle Collection Launch", objective="product_launch",
                 description="Introduce our new scented candle line to your audience.",
                 compensation_type="cash", cash_min=1800, cash_max=3500,
                 deliverables=[deliverable("instagram", "reel", 1)],
                 follower_min=4000, follower_max=50000, max_creators=10,
                 deadline="2026-11-18T23:59:59Z"),
        ],
    },
    {
        "slug": "streamplay-studios",
        "business_name": "StreamPlay Studios",
        "owner_name": "Aditya Menon",
        "email": "creators@streamplaystudios.test",
        "category": "Media & Entertainment",
        "industry": "Media & Entertainment",
        "city": "Mumbai",
        "address": "Film City Road, Goregaon East, Mumbai",
        "description": "Independent OTT and gaming content studio producing shows, shorts, and mobile games.",
        "website": "https://streamplaystudios.test",
        "instagram_handle": "@streamplay.studios",
        "niche": "entertainment",
        "campaigns": [
            dict(title="New Web Series Premiere Buzz", objective="event_promotion",
                 description="Hype up the premiere of our new comedy web series with a reaction/review.",
                 compensation_type="cash", cash_min=3000, cash_max=7000,
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("youtube", "short", 1)],
                 follower_min=20000, follower_max=200000, max_creators=6,
                 deadline="2026-09-22T23:59:59Z"),
            dict(title="Mobile Game Launch Gameplay", objective="product_launch",
                 description="Play and review our new mobile puzzle game ahead of launch.",
                 compensation_type="cash_and_product", cash_min=2500, cash_max=5000,
                 free_product="In-game premium pass + merch",
                 deliverables=[deliverable("youtube", "video", 1)],
                 follower_min=15000, follower_max=180000, max_creators=8,
                 deadline="2026-10-30T23:59:59Z"),
        ],
    },
    {
        "slug": "brightpath-academy",
        "business_name": "BrightPath Academy",
        "owner_name": "Sanya Joshi",
        "email": "partnerships@brightpathacademy.test",
        "category": "EdTech",
        "industry": "Education",
        "city": "Chennai",
        "address": "OMR Road, Chennai",
        "description": "Online academy offering exam-prep and skill courses for high schoolers and young pros.",
        "website": "https://brightpathacademy.test",
        "instagram_handle": "@brightpath.academy",
        "niche": "education",
        "campaigns": [
            dict(title="Exam Prep Course Launch", objective="product_launch",
                 description="Share how our exam-prep course helps students crack competitive exams.",
                 compensation_type="cash", cash_min=3000, cash_max=6000,
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "post", 1)],
                 follower_min=10000, follower_max=120000, max_creators=6,
                 deadline="2026-09-18T23:59:59Z"),
            dict(title="Study-With-Me Series", objective="user_generated_content",
                 description="Create a study-with-me video featuring our course dashboard.",
                 compensation_type="cash_and_product", cash_min=1500, cash_max=3500,
                 free_product="3-month course access",
                 deliverables=[deliverable("youtube", "video", 1)],
                 follower_min=5000, follower_max=80000, max_creators=10,
                 deadline="2026-10-12T23:59:59Z"),
            dict(title="Career Skills Bootcamp Promo", objective="brand_awareness",
                 description="Promote our new career-skills bootcamp for college students.",
                 compensation_type="product", free_product="Free bootcamp seat",
                 deliverables=[deliverable("instagram", "story", 3)],
                 follower_min=4000, follower_max=60000, max_creators=12,
                 deadline="2026-11-25T23:59:59Z"),
        ],
    },
    {
        "slug": "skyline-realty",
        "business_name": "Skyline Realty",
        "owner_name": "Varun Malhotra",
        "email": "marketing@skylinerealty.test",
        "category": "Real Estate",
        "industry": "Real Estate",
        "city": "Bengaluru",
        "address": "Sarjapur Road, Bengaluru",
        "description": "Boutique real estate brokerage specializing in premium apartments and villas in Bengaluru.",
        "website": "https://skylinerealty.test",
        "instagram_handle": "@skyline.realty",
        "niche": "real_estate",
        "campaigns": [
            dict(title="Luxury Apartment Walkthrough", objective="brand_awareness",
                 description="Film a walkthrough tour of our new premium apartment project.",
                 compensation_type="cash", cash_min=8000, cash_max=18000,
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("youtube", "video", 1)],
                 follower_min=15000, follower_max=150000, max_creators=3,
                 deadline="2026-10-02T23:59:59Z"),
            dict(title="Open House Weekend", objective="foot_traffic",
                 description="Attend our open house weekend and encourage followers to visit.",
                 compensation_type="cash", cash_min=4000, cash_max=9000,
                 deliverables=[deliverable("instagram", "story", 4)],
                 follower_min=8000, follower_max=90000, max_creators=4,
                 deadline="2026-11-08T23:59:59Z"),
        ],
    },
    {
        "slug": "torque-motors",
        "business_name": "Torque Motors",
        "owner_name": "Nikhil Bhatia",
        "email": "marketing@torquemotors.test",
        "category": "Automotive Dealership",
        "industry": "Automotive",
        "city": "Pune",
        "address": "Nagar Road, Pune",
        "description": "Multi-brand automotive dealership specializing in performance bikes and EV scooters.",
        "website": "https://torquemotors.test",
        "instagram_handle": "@torque.motors",
        "niche": "automotive",
        "campaigns": [
            dict(title="EV Scooter Test Ride", objective="product_launch",
                 description="Test ride and review our new electric scooter model.",
                 compensation_type="cash_and_product", cash_min=5000, cash_max=10000,
                 free_product="Free 1-month scooter loan",
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("youtube", "video", 1)],
                 follower_min=15000, follower_max=150000, max_creators=5,
                 deadline="2026-09-27T23:59:59Z"),
            dict(title="Weekend Ride Vlog", objective="brand_awareness",
                 description="Take one of our performance bikes on a weekend ride and vlog it.",
                 compensation_type="cash", cash_min=4000, cash_max=8000,
                 deliverables=[deliverable("youtube", "video", 1)],
                 follower_min=10000, follower_max=120000, max_creators=4,
                 deadline="2026-11-12T23:59:59Z"),
        ],
    },
    {
        "slug": "wealthwise-finance",
        "business_name": "WealthWise Finance",
        "owner_name": "Priyanka Sethi",
        "email": "growth@wealthwisefinance.test",
        "category": "FinTech",
        "industry": "Finance",
        "city": "Mumbai",
        "address": "BKC, Mumbai",
        "description": "Personal finance app helping young professionals budget, save, and invest.",
        "website": "https://wealthwisefinance.test",
        "instagram_handle": "@wealthwise.finance",
        "niche": "finance",
        "campaigns": [
            dict(title="App Launch — Budgeting Made Simple", objective="product_launch",
                 description="Walk your audience through setting up a budget on our app.",
                 compensation_type="cash", cash_min=4000, cash_max=9000,
                 deliverables=[deliverable("instagram", "reel", 1), deliverable("instagram", "post", 1)],
                 follower_min=10000, follower_max=150000, max_creators=6,
                 deadline="2026-10-18T23:59:59Z"),
            dict(title="Investing 101 Series", objective="user_generated_content",
                 description="Create a beginner-friendly explainer on investing using our app's tools.",
                 compensation_type="cash_and_product", cash_min=3000, cash_max=6000,
                 free_product="1-year premium subscription",
                 deliverables=[deliverable("youtube", "video", 1)],
                 follower_min=8000, follower_max=100000, max_creators=6,
                 deadline="2026-12-01T23:59:59Z"),
        ],
    },
]


def campaign_row(business_id: str, business_slug: str, niche: str, city: str, index: int, c: dict) -> dict:
    slug = f"{business_slug}-{index}"
    return {
        "id": seed_id("campaign", slug),
        "business_id": business_id,
        "title": c["title"],
        "objective": c["objective"],
        "description": c["description"],
        "deliverables": c["deliverables"],
        "compensation_type": c["compensation_type"],
        "cash_amount_min": c.get("cash_min"),
        "cash_amount_max": c.get("cash_max"),
        "free_product_description": c.get("free_product"),
        "creator_category": niche,
        "follower_range_min": c.get("follower_min"),
        "follower_range_max": c.get("follower_max"),
        "min_engagement_rate": c.get("engagement"),
        "location": c.get("location", city),
        "max_creators": c["max_creators"],
        "additional_requirements": c.get("additional_requirements"),
        "cover_image_url": cover_image(slug),
        "deadline": c["deadline"],
        "status": "active",
    }


def main() -> int:
    client = httpx.Client()
    total_campaigns = 0

    for biz in BUSINESSES:
        print(f"\n== {biz['business_name']} ({biz['niche']}) ==")

        create_auth_user(client, biz["email"], BUSINESS_PASSWORD, role="business")
        profile = find_profile_by_email(client, biz["email"])
        if profile is None:
            raise RuntimeError(
                f"Auth user created for {biz['email']} but no profiles row appeared -- "
                "check the on_auth_user_created trigger is applied."
            )
        profile_id = profile["id"]

        business_id = seed_id("business", biz["slug"])
        ensure_business_row(client, business_id, profile_id, biz)
        print(f"  business_id = {business_id}  login = {biz['email']} / {BUSINESS_PASSWORD}")

        rows = [
            campaign_row(business_id, biz["slug"], biz["niche"], biz["city"], i, c)
            for i, c in enumerate(biz["campaigns"], start=1)
        ]
        upsert(client, "campaigns", rows, on_conflict="id")
        total_campaigns += len(rows)
        print(f"  seeded {len(rows)} active campaigns")

    print("\n== summary ==")
    print(f"  {len(BUSINESSES)} businesses, {total_campaigns} campaigns across "
          f"{len({b['niche'] for b in BUSINESSES})} niches")
    print("  All business accounts share the password: " + BUSINESS_PASSWORD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
