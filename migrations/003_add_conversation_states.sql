CREATE TABLE conversation_states (
    customer_id VARCHAR(50) NOT NULL,
    step VARCHAR(30) NOT NULL DEFAULT 'menu',
    cart JSON NULL,
    pending_order_id INT NULL,
    status_order_lookup BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (customer_id)
);
