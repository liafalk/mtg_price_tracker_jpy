"""
SQLAlchemy models for the JPY MTG price tracker.

Schema shape:
    sets       -- one row per Hareruya "cardset" (maps to a Scryfall set)
    printings  -- one row per physical printing (set + collector number)
    prices     -- append-only log of price observations per printing/language

We deliberately keep `prices` append-only rather than upserting a single
row per printing, so we get historical trend data for free later.
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tier(str, enum.Enum):
    hot = "hot"
    warm = "warm"
    cold = "cold"


class Set(Base):
    """A Hareruya `cardset`, joined against a Scryfall set via product_code."""

    __tablename__ = "sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Hareruya identifiers
    hareruya_cardset_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    hareruya_product_code: Mapped[str | None] = mapped_column(String(32), index=True)
    
    name_jp: Mapped[str] = mapped_column(String(256))

    # Scryfall join key -- usually hareruya_product_code.lower(), but not
    # guaranteed (see sync_scryfall.py), so store it explicitly once resolved.
    set_code: Mapped[str | None] = mapped_column(String(16), index=True)

    release_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), default=Tier.cold, index=True)

    # bookkeeping
    last_crawled_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Set {self.hareruya_product_code} ({self.hareruya_cardset_id})>"


class Printing(Base):
    """A specific card printing: (set, collector_number)."""

    __tablename__ = "printings"
    __table_args__ = (
        UniqueConstraint("set_code", "collector_number", name="uq_set_collector_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    set_code: Mapped[str] = mapped_column(String(32), index=True)

    collector_number: Mapped[str] = mapped_column(String(16), index=True)
    name_en: Mapped[str] = mapped_column(String(256))
    name_jp: Mapped[str | None] = mapped_column(String(256))
    rarity: Mapped[str | None] = mapped_column(String(16))

    scryfall_id: Mapped[str] = mapped_column(String(36), index=True, nullable=True)
    scryfall_id_jp: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    img_grid_uri: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)
    img_thumb_uri: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)
    img_grid_uri_jp: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)
    img_thumb_uri_jp: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)

    double_faced: Mapped[bool] = mapped_column(Boolean, default=False)
    
    img_back_grid_uri: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)
    img_back_thumb_uri: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)
    img_back_grid_uri_jp: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)
    img_back_thumb_uri_jp: Mapped[str | None] = mapped_column(String(256), index=True, nullable=True)

    prices: Mapped[list["Price"]] = relationship(back_populates="printing")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Printing {self.name_en} #{self.collector_number}>"


class Language(str, enum.Enum):
    jp = "jp"
    en = "en"


class Price(Base):
    """
    Append-only price observation. One row per crawl per (printing, language).

    Storage is cheap; keeping every observation means price-history charts
    are just a query away later, with zero schema changes.
    """

    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    printing_id: Mapped[int] = mapped_column(ForeignKey("printings.id"), index=True)

    language: Mapped[Language] = mapped_column(Enum(Language))
    hareruya_product_id: Mapped[int] = mapped_column(Integer, index=True)

    price_yen: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    weekly_sales: Mapped[int] = mapped_column(Integer, default=0)
    foil: Mapped[bool] = mapped_column(Boolean, default=False)
    card_condition: Mapped[str | None] = mapped_column(String(8), nullable=True)

    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc), index=True
    )

    printing: Mapped["Printing"] = relationship(back_populates="prices")

    __table_args__ = (
        Index("ix_prices_printing_fetched", "printing_id", "fetched_at"),
    )
