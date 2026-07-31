CREATE TABLE superstore_sales (
    row_id INT PRIMARY KEY,
    order_id VARCHAR(30),
    order_date Text,
    ship_date Text,
    ship_mode VARCHAR(50),
    customer_id VARCHAR(30),
    customer_name VARCHAR(100),
    segment VARCHAR(50),
    country VARCHAR(50),
    city VARCHAR(100),
    state VARCHAR(100),
    postal_code VARCHAR(20),
    region VARCHAR(50),
    product_id VARCHAR(30),
    category VARCHAR(50),
    sub_category VARCHAR(50),
    product_name TEXT,
    sales NUMERIC(10,2),
    quantity INT,
    discount NUMERIC(5,2),
    profit NUMERIC(10,2)
);


SELECT * FROM superstore_sales;

SELECT * FROM superstore_sales LIMIT 10;

SELECT COUNT(*)
FROM superstore_sales;

SELECT *
FROM information_schema.columns
WHERE table_name='superstore_sales';


SELECT customer_name
FROM superstore_sales;

select customer_name,sales,profit from superstore_sales;

SELECT *
FROM superstore_sales
WHERE sales > 1000;

SELECT *
FROM superstore_sales
WHERE category='Technology';

SELECT *
FROM superstore_sales
ORDER BY sales DESC;

SELECT *
FROM superstore_sales
ORDER BY sales ASC;


SELECT *
FROM superstore_sales
LIMIT 5;

SELECT sales AS total_sales
FROM superstore_sales;

SELECT SUM(sales)
FROM superstore_sales;

SELECT AVG(sales)
FROM superstore_sales;

SELECT MIN(sales)
FROM superstore_sales;

SELECT MAX(sales)
FROM superstore_sales;

SELECT category,
COUNT(*)
FROM superstore_sales
GROUP BY category;

SELECT *
FROM superstore_sales
WHERE profit>500;

SELECT *
FROM superstore_sales
ORDER BY sales DESC
LIMIT 10;

SELECT category,
AVG(profit)
FROM superstore_sales
GROUP BY category;

