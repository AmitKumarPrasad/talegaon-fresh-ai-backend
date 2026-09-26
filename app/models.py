from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProductPriceHistoryModel(Base):
    __tablename__ = "product_price_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ProductModel(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    unit: Mapped[str] = mapped_column(String(30))
    price: Mapped[float] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)


class OrderModel(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    total: Mapped[float] = mapped_column(Float, default=0)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    razorpay_payment_link_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    razorpay_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    payment_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrderItemModel(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    line_total: Mapped[float] = mapped_column(Float)


class ProcessedWebhookModel(Base):
    __tablename__ = "processed_webhooks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(200))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint(
            "provider", "event_id", name="uq_processed_webhook_provider_event"
        ),
    )



class ConversationStateModel(Base):
    __tablename__ = "conversation_states"
    customer_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    step: Mapped[str] = mapped_column(String(30), default="menu")
    cart: Mapped[list] = mapped_column(JSON, default=list)
    pending_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_order_lookup: Mapped[bool] = mapped_column(Boolean, default=False)
