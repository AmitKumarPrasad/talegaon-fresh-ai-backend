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
    category: Mapped[str] = mapped_column(String(50), default="Other", nullable=False)
    price: Mapped[float] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class OrderModel(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    total: Mapped[float] = mapped_column(Float, default=0)
    delivery_fee: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    discount_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    razorpay_payment_link_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    razorpay_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    payment_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stock_reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    delivery_person_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_person_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    delivery_otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_otp_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    delivery_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional batch and payout inputs set by the authorized store admin.
    delivery_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    delivery_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_distance_km: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    delivery_incentive: Mapped[float] = mapped_column(Float, default=0, nullable=False)


class OrderStatusHistoryModel(Base):
    __tablename__ = "order_status_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class OrderItemModel(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    line_total: Mapped[float] = mapped_column(Float)


class OrderMessageModel(Base):
    __tablename__ = "order_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    sender: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class ProductRequestModel(Base):
    __tablename__ = "product_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.phone"), index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    request_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="NEW", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


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


class CustomerModel(Base):
    __tablename__ = "customers"
    phone: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="Customer")
    referral_code: Mapped[str | None] = mapped_column(
        String(24), unique=True, index=True, nullable=True
    )
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_request_count: Mapped[int] = mapped_column(Integer, default=0)
    otp_failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    otp_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_version: Mapped[int] = mapped_column(Integer, default=1)
    cart: Mapped[list] = mapped_column(JSON, default=list)
    fcm_token: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AddressModel(Base):
    __tablename__ = "addresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.phone"), index=True)
    label: Mapped[str] = mapped_column(String(50))
    address: Mapped[str] = mapped_column(String(500))
    city: Mapped[str] = mapped_column(String(100))
    pincode: Mapped[str] = mapped_column(String(6))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class DeliveryPartnerModel(Base):
    __tablename__ = "delivery_partners"
    phone: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    fcm_token: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DeliveryPartnerSessionModel(Base):
    __tablename__ = "delivery_partner_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    partner_phone: Mapped[str] = mapped_column(ForeignKey("delivery_partners.phone"), index=True)
    device_id: Mapped[str] = mapped_column(String(200), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryPayoutLedgerModel(Base):
    __tablename__ = "delivery_payout_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    partner_phone: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    payout_amount: Mapped[float] = mapped_column(Float, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, default=25, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    distance_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    incentive_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    cod_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class CheckoutRequestModel(Base):
    __tablename__ = "checkout_requests"
    customer_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)


class PromotionModel(Base):
    __tablename__ = "promotions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    discount_type: Mapped[str] = mapped_column(String(10), nullable=False)
    discount_value: Mapped[float] = mapped_column(Float, nullable=False)
    min_order: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    max_discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_order_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CampaignBannerModel(Base):
    __tablename__ = "campaign_banners"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
