select 
s.store_id,
sum(p.amount) as revenue
from store s
inner join staff sf
on sf.store_id=s.store_id
inner join payment p
on p.staff_id=sf.staff_id
group by s.store_id;

select 
c.name,
avg(f.rental_duration) as Duration
from category c
inner join film_category fc
on fc.category_id=c.category_id
inner join film f
on f.film_id=fc.film_id
group by c.name;

SELECT
    EXTRACT(MONTH FROM r.rental_date) AS month,
    COUNT(*) AS rentals_per_month
FROM rental r
GROUP BY EXTRACT(MONTH FROM r.rental_date)
ORDER BY month;

select 
c.name,
count (*) as total_films
from category c
inner join film_category fc
on fc.category_id=c.category_id
inner join film f
on f.film_id=fc.film_id
group by c.name
having count(*) > 50
order by total_films desc;


SELECT
c.customer_id,
c.first_name,
SUM(p.amount) AS total_spent
FROM customer c
INNER JOIN payment p
ON c.customer_id = p.customer_id
GROUP BY
c.customer_id,
c.first_name
HAVING SUM(p.amount) >
(
    SELECT AVG(customer_total)
    FROM
    (
        SELECT
            SUM(amount) AS customer_total
        FROM payment
        GROUP BY customer_id
    ) x
)
ORDER BY total_spent DESC;

SELECT
    c.name AS category,
    f.title,
    f.rental_rate
FROM category c
INNER JOIN film_category fc
    ON c.category_id = fc.category_id
INNER JOIN film f
    ON f.film_id = fc.film_id
WHERE f.rental_rate =
(
    SELECT MAX(f2.rental_rate)
    FROM film f2
    INNER JOIN film_category fc2
        ON f2.film_id = fc2.film_id
    WHERE fc2.category_id = fc.category_id
)
ORDER BY c.name;

SELECT
    customer_id,
    first_name,
    last_name
FROM customer
WHERE customer_id NOT IN
(
    SELECT customer_id
    FROM rental
);

SELECT
    s.store_id,
    SUM(p.amount) AS total_revenue
FROM store s
INNER JOIN staff st
    ON st.store_id = s.store_id
INNER JOIN payment p
    ON p.staff_id = st.staff_id
GROUP BY s.store_id
HAVING SUM(p.amount) =
(
    SELECT MAX(store_revenue)
    FROM
    (
        SELECT
            SUM(p.amount) AS store_revenue
        FROM store s
        INNER JOIN staff st
            ON st.store_id = s.store_id
        INNER JOIN payment p
            ON p.staff_id = st.staff_id
        GROUP BY s.store_id
    ) revenue
);

WITH customer_spending AS
(
    SELECT
        ci.city,
        c.customer_id,
        c.first_name,
        c.last_name,
        SUM(p.amount) AS total_spend
    FROM customer c
    INNER JOIN address a
        ON c.address_id = a.address_id
    INNER JOIN city ci
        ON a.city_id = ci.city_id
    INNER JOIN payment p
        ON p.customer_id = c.customer_id
    GROUP BY
        ci.city,
        c.customer_id,
        c.first_name,
        c.last_name
)

SELECT
    city,
    first_name,
    last_name,
    total_spend,
    RANK() OVER(
        PARTITION BY city
        ORDER BY total_spend DESC
    ) AS customer_rank
FROM customer_spending;

SELECT *
FROM
(
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        f.title,
        r.rental_date,
        ROW_NUMBER() OVER(
            PARTITION BY c.customer_id
            ORDER BY r.rental_date DESC
        ) AS rn
    FROM customer c
    INNER JOIN rental r
        ON c.customer_id = r.customer_id
    INNER JOIN inventory i
        ON r.inventory_id = i.inventory_id
    INNER JOIN film f
        ON i.film_id = f.film_id
) x
WHERE rn = 1;

WITH monthly_revenue AS
(
    SELECT
        DATE_TRUNC('month', payment_date) AS month,
        SUM(amount) AS revenue
    FROM payment
    GROUP BY DATE_TRUNC('month', payment_date)
)

SELECT
    month,
    revenue,
    LAG(revenue) OVER(ORDER BY month) AS previous_month,
    revenue - LAG(revenue) OVER(ORDER BY month) AS growth
FROM monthly_revenue;


WITH film_revenue AS
(
    SELECT
        c.name AS category,
        f.title,
        SUM(p.amount) AS revenue
    FROM category c
    INNER JOIN film_category fc
        ON c.category_id = fc.category_id
    INNER JOIN film f
        ON fc.film_id = f.film_id
    INNER JOIN inventory i
        ON f.film_id = i.film_id
    INNER JOIN rental r
        ON i.inventory_id = r.inventory_id
    INNER JOIN payment p
        ON r.rental_id = p.rental_id
    GROUP BY
        c.name,
        f.title
)

SELECT *
FROM
(
    SELECT
        *,
        RANK() OVER(
            PARTITION BY category
            ORDER BY revenue DESC
        ) AS film_rank
    FROM film_revenue
) x
WHERE film_rank <= 3;


WITH staff_revenue AS
(
    SELECT
        st.store_id,
        st.staff_id,
        st.first_name,
        st.last_name,
        SUM(p.amount) AS revenue
    FROM staff st
    INNER JOIN payment p
        ON st.staff_id = p.staff_id
    GROUP BY
        st.store_id,
        st.staff_id,
        st.first_name,
        st.last_name
),

store_revenue AS
(
    SELECT
        store_id,
        SUM(revenue) AS total_store_revenue
    FROM staff_revenue
    GROUP BY store_id
)

SELECT *
FROM
(
    SELECT
        sr.store_id,
        sr.staff_id,
        sr.first_name,
        sr.last_name,
        sr.revenue,
        st.total_store_revenue,
        ROUND((sr.revenue * 100.0) / st.total_store_revenue,2) AS percentage,
        RANK() OVER(
            PARTITION BY sr.store_id
            ORDER BY sr.revenue DESC
        ) AS staff_rank
    FROM staff_revenue sr
    INNER JOIN store_revenue st
        ON sr.store_id = st.store_id
) x
WHERE staff_rank = 1;