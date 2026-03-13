from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean, JSON, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.database import Base


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(20))  # "zillow" or "redfin"
    source_id = Column(String(100), unique=True, index=True)  # zpid or redfin property_id
    url = Column(Text, nullable=False)

    # Core property details
    address = Column(String(500))
    city = Column(String(100), default="Barrington")
    state = Column(String(2), default="RI")
    zipcode = Column(String(10))
    latitude = Column(Float)
    longitude = Column(Float)

    price = Column(Integer)
    bedrooms = Column(Integer)
    bathrooms = Column(Float)
    sqft = Column(Integer)
    lot_sqft = Column(Integer)
    year_built = Column(Integer)
    property_type = Column(String(50))  # single_family, condo, townhouse
    status = Column(String(30))  # active, pending, sold

    # Extra details
    description = Column(Text)
    features = Column(JSON)  # {"interior": [...], "exterior": [...], ...}
    photos = Column(JSON)  # list of photo URLs
    price_history = Column(JSON)  # [{date, price, event}, ...]
    tax_info = Column(JSON)  # {annual_tax, assessed_value}
    hoa_fee = Column(Integer)

    # Timestamps
    listed_date = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    scores = relationship("ListingScore", back_populates="listing", uselist=False,
                          cascade="all, delete-orphan")
    comps = relationship("Comp", back_populates="listing", cascade="all, delete-orphan")
    notes = relationship("UserNote", back_populates="listing", cascade="all, delete-orphan")
    ai_summary = relationship("AISummary", back_populates="listing", uselist=False,
                              cascade="all, delete-orphan")


class ListingScore(Base):
    __tablename__ = "listing_scores"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), unique=True)

    # Price analysis
    price_score = Column(Float)  # -1 to 1 scale (-1 = overpriced, 1 = underpriced)
    price_per_sqft = Column(Float)
    median_comp_price_per_sqft = Column(Float)
    price_vs_comps_pct = Column(Float)  # % above/below comp median

    # Location scores (1-10)
    school_score = Column(Float)
    elementary_school = Column(String(200))
    middle_school = Column(String(200))
    high_school = Column(String(200))
    school_details = Column(JSON)

    walkability_score = Column(Integer)
    flood_risk = Column(String(20))  # "minimal", "moderate", "high", "severe"
    flood_details = Column(JSON)

    # Composite
    overall_score = Column(Float)  # weighted composite 1-10

    scored_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    listing = relationship("Listing", back_populates="scores")


class Comp(Base):
    __tablename__ = "comps"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"))

    address = Column(String(500))
    sold_price = Column(Integer)
    sold_date = Column(DateTime)
    bedrooms = Column(Integer)
    bathrooms = Column(Float)
    sqft = Column(Integer)
    year_built = Column(Integer)
    price_per_sqft = Column(Float)
    distance_miles = Column(Float)
    source_url = Column(Text)

    listing = relationship("Listing", back_populates="comps")


class UserNote(Base):
    __tablename__ = "user_notes"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"))

    content = Column(Text, nullable=False)
    rating = Column(Integer)  # 1-5 stars
    visited = Column(Boolean, default=False)
    visit_date = Column(DateTime)
    tags = Column(JSON)  # ["loved kitchen", "busy street", "needs work"]

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    listing = relationship("Listing", back_populates="notes")


class AISummary(Base):
    __tablename__ = "ai_summaries"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), unique=True)

    summary = Column(Text)  # Claude-generated narrative
    pros = Column(JSON)  # ["Great school district", ...]
    cons = Column(JSON)  # ["Above market price", ...]
    verdict = Column(String(50))  # "strong_buy", "fair_deal", "overpriced", "pass"

    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    listing = relationship("Listing", back_populates="ai_summary")
