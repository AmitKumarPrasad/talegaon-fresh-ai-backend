CREATE TABLE processed_webhooks (
    id INT NOT NULL AUTO_INCREMENT,
    provider VARCHAR(30) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_processed_webhook_provider_event UNIQUE (provider, event_id)
);
