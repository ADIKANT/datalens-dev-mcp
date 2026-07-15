SELECT
    min(payment_at) AS payment_at
FROM payments
GROUP BY order_id
