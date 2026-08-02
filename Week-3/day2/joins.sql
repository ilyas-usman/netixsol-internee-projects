SELECT
    tc.table_name,
    kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'PRIMARY KEY'
ORDER BY tc.table_name;


SELECT
    tc.table_name,
    kcu.column_name AS foreign_key,
    ccu.table_name AS references_table,
    ccu.column_name AS references_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_schema='public'
ORDER BY tc.table_name;

SELECT
    c.first_name,
    c.last_name,
    c.email,
    ci.city,
    co.country
FROM customer c
INNER JOIN address a
    ON c.address_id = a.address_id
INNER JOIN city ci
    ON a.city_id = ci.city_id
INNER JOIN country co
    ON ci.country_id = co.country_id;


SELECT
    c.first_name,
    c.last_name,
    f.title,
    p.amount
FROM payment p
INNER JOIN customer c
    ON p.customer_id = c.customer_id
INNER JOIN rental r
    ON p.rental_id = r.rental_id
INNER JOIN inventory i
    ON r.inventory_id = i.inventory_id
INNER JOIN film f
    ON i.film_id = f.film_id;


select 
	c.first_name,
	c.customer_id,
	c.last_name,
	sum(p.amount) as total_spent
from customer c
inner join payment p
	on c.customer_id=p.customer_id
	GROUP BY c.customer_id,c.first_name,c.last_name
	order by total_spent desc
	limit 10;

select 
	f.title,
	f.rental_rate,
	c.name
from film f
join film_category fg
on fg.film_id=f.film_id
join category c
on c.category_id=fg.category_id;


SELECT
    a.first_name,
    a.last_name,
    f.title
FROM actor a
INNER JOIN film_actor fa
    ON fa.actor_id = a.actor_id
INNER JOIN film f
    ON f.film_id = fa.film_id;


SELECT
    c.name AS category_name,
    COUNT(fc.film_id) AS total_films
FROM category c
INNER JOIN film_category fc
    ON c.category_id = fc.category_id
GROUP BY c.name
ORDER BY total_films DESC;

SELECT
    c.name AS category,
    SUM(p.amount) AS total_revenue
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
GROUP BY c.name
ORDER BY total_revenue DESC;

SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    COUNT(r.rental_id) AS total_rentals
FROM customer c
INNER JOIN rental r
    ON c.customer_id = r.customer_id
GROUP BY
    c.customer_id,
    c.first_name,
    c.last_name
HAVING COUNT(r.rental_id) > 20
ORDER BY total_rentals DESC;

SELECT
    c.city,
    SUM(p.amount) AS revenue
FROM city c
INNER JOIN address a
    ON c.city_id = a.city_id
INNER JOIN customer cu
    ON a.address_id = cu.address_id
INNER JOIN payment p
    ON cu.customer_id = p.customer_id
GROUP BY c.city
ORDER BY revenue DESC;


SELECT
    a.actor_id,
    a.first_name,
    a.last_name,
    SUM(p.amount) AS total_revenue
FROM actor a
INNER JOIN film_actor fa
    ON a.actor_id = fa.actor_id
INNER JOIN film f
    ON fa.film_id = f.film_id
INNER JOIN inventory i
    ON f.film_id = i.film_id
INNER JOIN rental r
    ON i.inventory_id = r.inventory_id
INNER JOIN payment p
    ON r.rental_id = p.rental_id
GROUP BY
    a.actor_id,
    a.first_name,
    a.last_name
ORDER BY total_revenue DESC
LIMIT 1;