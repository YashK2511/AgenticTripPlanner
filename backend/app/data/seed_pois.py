import json
import logging
from sqlalchemy.orm import Session
from app.models.db_models import POICandidateModel, POIEmbeddingModel
from app.services.embedding_service import encode_batch
from app.core.config import settings
from datetime import datetime, timezone

logger = logging.getLogger("trip_planner.data.seed")

# High-quality dummy dataset for testing vector retrieval
SEED_DATA = [
    # ─── GOA ─────────────────────────────────────────────
    {
        "id": "goa_poi_001",
        "name": "Baga Beach",
        "city": "Goa",
        "category": "Beach",
        "description": "One of North Goa's most popular beaches, known for its lively nightlife, water sports, and beach shacks serving excellent seafood.",
        "coordinates_lat": 15.5523,
        "coordinates_lng": 73.7516,
        "visit_duration": 180,
        "cost_range_min": 0,
        "cost_range_max": 2000,
        "accessibility_json": {"wheelchair_accessible": False},
        "opening_hours_json": {"monday": "00:00-23:59", "open_247": True}
    },
    {
        "id": "goa_poi_002",
        "name": "Basilica of Bom Jesus",
        "city": "Goa",
        "category": "Historic Site",
        "description": "A UNESCO World Heritage site and historic Portuguese church dating back to 1605. Famous for holding the mortal remains of St. Francis Xavier.",
        "coordinates_lat": 15.5009,
        "coordinates_lng": 73.9116,
        "visit_duration": 90,
        "cost_range_min": 0,
        "cost_range_max": 0,
        "accessibility_json": {"wheelchair_accessible": True},
        "opening_hours_json": {"monday": "09:00-18:30"}
    },
    {
        "id": "goa_poi_003",
        "name": "Thalassa",
        "city": "Goa",
        "category": "Restaurant",
        "description": "Upscale Greek tavern located on a cliff top overlooking the Arabian ocean. Known for stunning sunsets, seafood, and live entertainment.",
        "coordinates_lat": 15.6267,
        "coordinates_lng": 73.7388,
        "visit_duration": 120,
        "cost_range_min": 1500,
        "cost_range_max": 4000,
        "accessibility_json": {"wheelchair_accessible": True, "parking": True},
        "opening_hours_json": {"monday": "10:00-23:30"}
    },
    {
        "id": "goa_poi_004",
        "name": "Dudhsagar Waterfalls",
        "city": "Goa",
        "category": "Nature",
        "description": "A majestic four-tiered waterfall located on the Mandovi River. Needs a jeep safari through the Bhagwan Mahaveer Sanctuary to reach. Great for hiking and jungle adventure.",
        "coordinates_lat": 15.3144,
        "coordinates_lng": 74.3143,
        "visit_duration": 300,
        "cost_range_min": 800,
        "cost_range_max": 1500,
        "accessibility_json": {"wheelchair_accessible": False, "requires_hiking": True},
        "opening_hours_json": {"monday": "07:00-16:30"}
    },
    {
        "id": "goa_poi_005",
        "name": "Taj Exotica Resort & Spa",
        "city": "Goa",
        "category": "Hotel",
        "description": "Luxury Mediterranean-style 5-star beachfront resort located in Benaulim, South Goa. Features a spa, golf, fine dining, and excellent accessibility.",
        "coordinates_lat": 15.2530,
        "coordinates_lng": 73.9161,
        "visit_duration": 1440,
        "cost_range_min": 25000,
        "cost_range_max": 50000,
        "accessibility_json": {"wheelchair_accessible": True, "elevators": True},
        "opening_hours_json": {"open_247": True}
    },

    # ─── MANALI ──────────────────────────────────────────
    {
        "id": "man_poi_001",
        "name": "Solang Valley",
        "city": "Manali",
        "category": "Adventure",
        "description": "Famous for adventure sports like paragliding, skiing, and zorbing. Offers spectacular views of the snow-capped Himalayan peaks.",
        "coordinates_lat": 32.3168,
        "coordinates_lng": 77.1578,
        "visit_duration": 240,
        "cost_range_min": 1000,
        "cost_range_max": 5000,
        "accessibility_json": {"wheelchair_accessible": False, "requires_walking": True},
        "opening_hours_json": {"monday": "09:00-18:00"}
    },
    {
        "id": "man_poi_002",
        "name": "Hadimba Temple",
        "city": "Manali",
        "category": "Historic Site",
        "description": "An ancient cave temple built in 1553, surrounded by a gorgeous cedar forest. Famous for its wooden architecture.",
        "coordinates_lat": 32.2468,
        "coordinates_lng": 77.1818,
        "visit_duration": 60,
        "cost_range_min": 0,
        "cost_range_max": 50,
        "accessibility_json": {"wheelchair_accessible": False, "stairs_present": True},
        "opening_hours_json": {"monday": "08:00-18:00"}
    },
    {
        "id": "man_poi_003",
        "name": "Johnson's Cafe",
        "city": "Manali",
        "category": "Restaurant",
        "description": "Iconic cafe in Manali known for its wood-fired pizzas, baked trout, and cozy fire-lit ambiance.",
        "coordinates_lat": 32.2432,
        "coordinates_lng": 77.1873,
        "visit_duration": 90,
        "cost_range_min": 800,
        "cost_range_max": 2000,
        "accessibility_json": {"wheelchair_accessible": True},
        "opening_hours_json": {"monday": "09:00-23:00"}
    },
    {
        "id": "man_poi_004",
        "name": "Rohtang Pass",
        "city": "Manali",
        "category": "Nature",
        "description": "High mountain pass offering breathtaking panoramic views of the Himalayas. Great for snow activities. Only open in summer.",
        "coordinates_lat": 32.3716,
        "coordinates_lng": 77.2466,
        "visit_duration": 360,
        "cost_range_min": 500,
        "cost_range_max": 1500,
        "accessibility_json": {"wheelchair_accessible": False},
        "opening_hours_json": {"monday": "06:00-17:00"}
    },
]


def _build_embedding_text(poi: dict) -> str:
    """Format POI metadata into a dense string for the embedding model to encode."""
    return f"{poi['name']}. {poi['category']} in {poi['city']}. {poi['description']}"


def seed_database(db: Session):
    """
    Populates the database with curated POIs and their vector embeddings.
    Idempotent operation (skips completely if data is already present).
    """
    count = db.query(POICandidateModel).count()
    if count > 0:
        logger.info("Database already seeded with %d POIs. Skipping.", count)
        return

    logger.info("Starting POI data seeding pipeline (%d records)", len(SEED_DATA))

    # 1. Insert tabular metadata
    poi_models = []
    texts_to_embed = []

    for row in SEED_DATA:
        # Create standard evidence metadata
        evidence = {
            "source_id": "seed_data_v1",
            "source_type": "internal_db",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "url": None
        }

        poi = POICandidateModel(
            id=row["id"],
            name=row["name"],
            # Append city to description for normal text search if needed later
            description=f"{row['description']} located in {row['city']}",
            category=row["category"],
            coordinates_lat=row["coordinates_lat"],
            coordinates_lng=row["coordinates_lng"],
            visit_duration=row["visit_duration"],
            cost_range_min=row["cost_range_min"],
            cost_range_max=row["cost_range_max"],
            accessibility_json=row["accessibility_json"],
            opening_hours_json=row["opening_hours_json"],
            evidence_json=evidence,
            relevance_score=1.0  # Default base score
        )
        poi_models.append(poi)
        texts_to_embed.append(_build_embedding_text(row))

    db.add_all(poi_models)
    db.flush()  # Ensure inserted

    # 2. Run embedding algorithm (batch)
    logger.info("Generating embeddings for POIs using %s...", settings.EMBEDDING_MODEL)
    embeddings = encode_batch(texts_to_embed)

    # 3. Store embeddings
    embedding_models = []
    for row, embed in zip(SEED_DATA, embeddings):
        model = POIEmbeddingModel(
            poi_id=row["id"],
            embedding_json=embed,
            model_name=settings.EMBEDDING_MODEL
        )
        embedding_models.append(model)

    db.add_all(embedding_models)
    db.commit()

    logger.info("Successfully seeded %d POIs with embeddings.", len(SEED_DATA))
