from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    default_shop_id: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    watched: Mapped[list["WatchedProduct"]] = relationship(back_populates="user")


class WatchedProduct(Base):
    __tablename__ = "watched_products"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "sku", "shop_id", name="uq_watchlist_item"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_user_id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(32))
    sku: Mapped[str] = mapped_column(String(64), index=True)
    shop_id: Mapped[int] = mapped_column(Integer)
    name_cache: Mapped[str] = mapped_column(String(512))
    url_key: Mapped[str | None] = mapped_column(String(512))
    notify_min_discount_percent: Mapped[int] = mapped_column(Integer, default=1)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="watched")


class ProductState(Base):
    __tablename__ = "product_state"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    shop_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    special_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    discount_percent: Mapped[int | None] = mapped_column(Integer)
    special_price_to_date: Mapped[datetime | None] = mapped_column(Date)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationSent(Base):
    __tablename__ = "notifications_sent"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_user_id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(32))
    sku: Mapped[str] = mapped_column(String(64), index=True)
    shop_id: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    discount_percent_at_notify: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
