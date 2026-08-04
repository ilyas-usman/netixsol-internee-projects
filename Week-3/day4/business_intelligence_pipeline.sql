-- ==========================================================
-- Week 3 Day 4
-- Advanced SQL Business Intelligence Challenge
-- Music Store Database
-- ==========================================================
------------------------------------------------------------
-- Customer Spending Profile
------------------------------------------------------------
WITH customer_profile AS
(
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        SUM(i.total) AS total_spent,
        COUNT(DISTINCT i.invoice_id) AS total_invoices,
        COUNT(il.invoice_line_id) AS total_tracks,
        COUNT(DISTINCT t.genre_id) AS unique_genres,
        COUNT(DISTINCT al.artist_id) AS unique_artists,
        COUNT(DISTINCT DATE_TRUNC('month', i.invoice_date)) AS purchase_months,
        AVG(i.total) AS avg_invoice
    FROM customer c
    INNER JOIN invoice i
        ON c.customer_id = i.customer_id
    INNER JOIN invoice_line il
        ON i.invoice_id = il.invoice_id
    INNER JOIN track t
        ON il.track_id = t.track_id
    INNER JOIN album al
        ON t.album_id = al.album_id
    GROUP BY
        c.customer_id,
        c.first_name,
        c.last_name
),
------------------------------------------------------------
-- Customer Segmentation
------------------------------------------------------------
customer_segment AS
(
    SELECT
        *,
        CASE
            WHEN total_spent > 100
                 AND total_invoices > 10
                 AND unique_genres > 5
                 AND unique_artists > 8
            THEN 'Platinum'
            WHEN total_spent >= 80
                 AND total_invoices >= 8
                 AND unique_genres >= 3
                 AND unique_artists >= 6
            THEN 'Gold'
            WHEN total_spent >= 65
                 AND total_invoices > 6
                 AND unique_genres >= 2
                 AND unique_artists >= 4
            THEN 'Silver'
            ELSE 'Bronze'
        END AS customer_segment
    FROM customer_profile
),
------------------------------------------------------------
-- Favorite Genre for Each Customer
------------------------------------------------------------
favorite_genre AS
(
    SELECT
        customer_id,
        genre_name
    FROM
    (
        SELECT
            c.customer_id,
            g.name AS genre_name,
            COUNT(*) AS purchases,
            ROW_NUMBER() OVER
            (
                PARTITION BY c.customer_id
                ORDER BY COUNT(*) DESC
            ) AS genre_rank
        FROM customer c
        JOIN invoice i
            ON c.customer_id=i.customer_id
        JOIN invoice_line il
            ON i.invoice_id=il.invoice_id
        JOIN track t
            ON il.track_id=t.track_id
        JOIN genre g
            ON t.genre_id=g.genre_id
        GROUP BY
            c.customer_id,
            g.name
    ) x
    WHERE genre_rank=1
),
------------------------------------------------------------
-- Country Performance Metrics
------------------------------------------------------------
country_metrics AS
(
    SELECT
        c.country,
        SUM(i.total) AS total_revenue,
        COUNT(DISTINCT c.customer_id) AS total_customers,
        SUM(i.total) / COUNT(DISTINCT c.customer_id) AS avg_revenue_per_customer,
        AVG(i.total) AS avg_invoice_value,
        COUNT(DISTINCT t.genre_id) AS genre_diversity
    FROM customer c
    JOIN invoice i
        ON c.customer_id = i.customer_id
    JOIN invoice_line il
        ON i.invoice_id = il.invoice_id
    JOIN track t
        ON il.track_id = t.track_id
    GROUP BY c.country
),
------------------------------------------------------------
-- Country Performance Score
------------------------------------------------------------
country_score AS
(
    SELECT
        *,
        (
            total_revenue * 0.40
            + avg_revenue_per_customer * 0.20
            + avg_invoice_value * 0.20
            + genre_diversity * 0.10
            + total_customers * 0.10
        ) AS performance_score
    FROM country_metrics
),
------------------------------------------------------------
-- Country Ranking
------------------------------------------------------------
country_rank AS
(
    SELECT
        *,
        RANK() OVER
        (
            ORDER BY performance_score DESC
        ) AS country_rank
    FROM country_score
),
------------------------------------------------------------
-- Employee Revenue
------------------------------------------------------------
employee_revenue AS
(
    SELECT
        e.employee_id,
        e.first_name,
        e.last_name,
        SUM(i.total) AS revenue,
        RANK() OVER(ORDER BY SUM(i.total) DESC) AS emp_rank
    FROM employee e
    JOIN customer c
        ON e.employee_id = c.support_rep_id
    JOIN invoice i
        ON c.customer_id = i.customer_id
    GROUP BY
        e.employee_id,
        e.first_name,
        e.last_name
),
------------------------------------------------------------
-- Artist Revenue
------------------------------------------------------------
artist_revenue AS
(
    SELECT
        ar.artist_id,
        ar.name,
        SUM(il.unit_price * il.quantity) AS revenue,
        RANK() OVER
        (
            ORDER BY SUM(il.unit_price * il.quantity) DESC
        ) AS artist_rank
    FROM artist ar
    JOIN album al
        ON ar.artist_id = al.artist_id
    JOIN track t
        ON al.album_id = t.album_id
    JOIN invoice_line il
        ON t.track_id = il.track_id
    GROUP BY
        ar.artist_id,
        ar.name
),
------------------------------------------------------------
-- Album Revenue
------------------------------------------------------------
album_revenue AS
(
    SELECT
        al.album_id,
        al.title,
        SUM(il.unit_price * il.quantity) AS revenue,
        RANK() OVER
        (
            ORDER BY SUM(il.unit_price * il.quantity) DESC
        ) AS album_rank
    FROM album al
    JOIN track t
        ON al.album_id=t.album_id
    JOIN invoice_line il
        ON t.track_id=il.track_id
    GROUP BY
        al.album_id,
        al.title
)
SELECT
cs.customer_segment,
COUNT(*) AS customers,
SUM(cs.total_spent) AS revenue,
AVG(cs.avg_invoice) AS average_invoice
FROM customer_segment cs
GROUP BY
cs.customer_segment;
-- Customer Segments
SELECT *
FROM customer_segment;
-- Favorite Genres
SELECT *
FROM favorite_genre;
-- Country Metrics
SELECT *
FROM country_metrics;
-- Country Ranking
SELECT *
FROM country_rank
ORDER BY country_rank;
-- Artist Revenue
SELECT *
FROM artist_revenue
ORDER BY artist_rank;
------------------------------------------------------------
-- Customer Segment Summary
------------------------------------------------------------
SELECT
    cs.customer_segment,
    COUNT(*) AS customers,
    SUM(cs.total_spent) AS revenue,
    AVG(cs.avg_invoice) AS average_invoice
FROM customer_segment cs
GROUP BY cs.customer_segment
ORDER BY revenue DESC;
------------------------------------------------------------
-- Revenue by Segment
------------------------------------------------------------
SELECT
    customer_segment,
    SUM(total_spent) AS revenue
FROM customer_segment
GROUP BY customer_segment
ORDER BY revenue DESC;
------------------------------------------------------------
-- Top Customer in Each Segment
------------------------------------------------------------
SELECT *
FROM
(
    SELECT
        customer_segment,
        customer_id,
        first_name,
        last_name,
        total_spent,
        ROW_NUMBER() OVER
        (
            PARTITION BY customer_segment
            ORDER BY total_spent DESC
        ) AS rn
    FROM customer_segment
) x
WHERE rn = 1;
------------------------------------------------------------
-- Top Genre in Each Segment
------------------------------------------------------------
SELECT
    cs.customer_segment,
    fg.genre_name,
    COUNT(*) AS customers
FROM customer_segment cs
JOIN favorite_genre fg
ON cs.customer_id = fg.customer_id
GROUP BY
    cs.customer_segment,
    fg.genre_name
ORDER BY
    cs.customer_segment,
    customers DESC;
------------------------------------------------------------
-- Best Performing Country
------------------------------------------------------------
SELECT *
FROM country_rank
WHERE country_rank = 1;
------------------------------------------------------------
-- Revenue Contribution by Country
------------------------------------------------------------
SELECT
    country,
    total_revenue,
    ROUND
    (
        total_revenue * 100.0 /
        SUM(total_revenue) OVER(),
        2
    ) AS contribution_percent
FROM country_rank
ORDER BY contribution_percent DESC;
------------------------------------------------------------
-- Top Employee by Revenue
------------------------------------------------------------
SELECT *
FROM employee_revenue
WHERE emp_rank = 1;
------------------------------------------------------------
-- Personalized Marketing Recommendation
------------------------------------------------------------

SELECT
    cs.customer_id,
    cs.first_name,
    cs.last_name,
    cs.customer_segment,
    fg.genre_name,
    CASE
        WHEN cs.customer_segment='Platinum'
        THEN 'Early Access to New Releases'
        WHEN cs.customer_segment='Gold'
        THEN 'Album Bundles'
        WHEN cs.customer_segment='Silver'
        THEN 'Genre Discounts'
        ELSE 'First Purchase Coupon'
    END AS recommendation
FROM customer_segment cs
JOIN favorite_genre fg
ON cs.customer_id = fg.customer_id;


--Question no 1
WITH customer_profile AS
(
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        SUM(i.total) AS total_spent,
        COUNT(DISTINCT i.invoice_id) AS total_invoices,
        COUNT(il.invoice_line_id) AS total_tracks,
        COUNT(DISTINCT t.genre_id) AS unique_genres,
        COUNT(DISTINCT al.artist_id) AS unique_artists,
        COUNT(DISTINCT DATE_TRUNC('month', i.invoice_date)) AS purchase_months,
        AVG(i.total) AS avg_invoice
    FROM customer c
    INNER JOIN invoice i
        ON c.customer_id = i.customer_id
    INNER JOIN invoice_line il
        ON i.invoice_id = il.invoice_id
    INNER JOIN track t
        ON il.track_id = t.track_id
    INNER JOIN album al
        ON t.album_id = al.album_id
    GROUP BY
        c.customer_id,
        c.first_name,
        c.last_name
)
SELECT *
FROM customer_profile
ORDER BY total_spent DESC;

--Question no 2

customer_segment AS
(
    SELECT
        *,
        CASE
            WHEN total_spent > 100
                 AND total_invoices > 10
                 AND unique_genres > 5
                 AND unique_artists > 8
            THEN 'Platinum'
            WHEN total_spent >= 80
                 AND total_invoices >= 8
                 AND unique_genres >= 3
                 AND unique_artists >= 6
            THEN 'Gold'
            WHEN total_spent >= 65
                 AND total_invoices > 6
                 AND unique_genres >= 2
                 AND unique_artists >= 4
            THEN 'Silver'
            ELSE 'Bronze'
        END AS customer_segment
    FROM customer_profile
)
SELECT *
FROM customer_segment;

--Question no 3

favorite_genre AS
(
    SELECT
        customer_id,
        genre_name
    FROM
    (
        SELECT
            c.customer_id,
            g.name AS genre_name,
            COUNT(*) AS purchases,
            ROW_NUMBER() OVER
            (
                PARTITION BY c.customer_id
                ORDER BY COUNT(*) DESC
            ) AS genre_rank
        FROM customer c
        JOIN invoice i
            ON c.customer_id=i.customer_id
        JOIN invoice_line il
            ON i.invoice_id=il.invoice_id
        JOIN track t
            ON il.track_id=t.track_id
        JOIN genre g
            ON t.genre_id=g.genre_id
        GROUP BY
            c.customer_id,
            g.name
    ) x
    WHERE genre_rank=1
)
SELECT
cs.customer_id,
cs.first_name,
cs.last_name,
cs.customer_segment,
fg.genre_name,
CASE
WHEN cs.customer_segment='Platinum'
THEN 'Early access to new releases'
WHEN cs.customer_segment='Gold'
THEN 'Album Bundles'
WHEN cs.customer_segment='Silver'
THEN 'Genre Discounts'
ELSE 'First Purchase Coupon'
END AS recommendation
FROM customer_segment cs
JOIN favorite_genre fg
ON cs.customer_id=fg.customer_id;

--Question no 4
WITH country_metrics AS
(
    SELECT
        c.country,

        SUM(i.total) AS total_revenue,

        COUNT(DISTINCT c.customer_id) AS total_customers,

        SUM(i.total) / COUNT(DISTINCT c.customer_id) AS avg_revenue_per_customer,

        AVG(i.total) AS avg_invoice_value,

        COUNT(DISTINCT t.genre_id) AS genre_diversity

    FROM customer c

    JOIN invoice i
        ON c.customer_id = i.customer_id

    JOIN invoice_line il
        ON i.invoice_id = il.invoice_id

    JOIN track t
        ON il.track_id = t.track_id

    GROUP BY c.country
),

country_score AS
(
    SELECT
        *,

        (
            total_revenue * 0.40
            + avg_revenue_per_customer * 0.20
            + avg_invoice_value * 0.20
            + genre_diversity * 0.10
            + total_customers * 0.10
        ) AS performance_score

    FROM country_metrics
),

country_rank AS
(
    SELECT
        *,

        RANK() OVER
        (
            ORDER BY performance_score DESC
        ) AS country_rank

    FROM country_score
)

SELECT *
FROM country_rank
ORDER BY country_rank;