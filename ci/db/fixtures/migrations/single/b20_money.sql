-- expect: S-MONEY-1
-- mookko:phase expand
CREATE TABLE __SCHEMA__.payments (
    payment_id uuid PRIMARY KEY,
    amount numeric(12, 2) NOT NULL,
    rate double precision
);
