ALTER TABLE orders
    ADD COLUMN payment_link_url VARCHAR(500) NULL,
    ADD COLUMN razorpay_payment_link_id VARCHAR(100) NULL,
    ADD COLUMN razorpay_payment_id VARCHAR(100) NULL,
    ADD COLUMN razorpay_event_id VARCHAR(100) NULL,
    ADD COLUMN payment_verified_at DATETIME NULL;

CREATE UNIQUE INDEX uq_orders_razorpay_payment_link_id
    ON orders (razorpay_payment_link_id);

CREATE UNIQUE INDEX uq_orders_razorpay_payment_id
    ON orders (razorpay_payment_id);

CREATE UNIQUE INDEX uq_orders_razorpay_event_id
    ON orders (razorpay_event_id);
