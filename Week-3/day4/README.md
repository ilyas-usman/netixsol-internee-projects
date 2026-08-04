# Week 3 Day 4 Advanced SQL Business Intelligence Challenge (Music Store Database)
#### Dataset
#### Music Store Database (PostgreSQL)
##### Segmentation logic and justification.
Customers were classified into Platinum, Gold, Silver, and Bronze based on total spending, purchase frequency, genre diversity, and artist diversity.
##### Country ranking methodology.
Countries were ranked using a weighted performance score based on total revenue, customers, average revenue per customer, average invoice value, and genre diversity.
##### Marketing Recommendation Strategy
Each customer segment was assigned a different promotional campaign based on its favorite genre and purchasing behavior.
##### At least 5 actionable recommendations.
- Offer early access to new releases for Platinum customers.
- Provide album bundle discounts for Gold customers.
- Give genre-based discounts to Silver customers.
- Send first purchase coupons to Bronze customers.
- Expand business in the top-ranked countries with the highest performance scores.
##### Challenges faced and how they were solved.
Understanding multi-level CTEs was difficult, so the query was built step by step using reusable CTEs.
#### Task 2 — Customer Segmentation
Using the customer profile from Task 1:
Classify every customer into one of four segments:
Platinum,Gold,Silver,Bronze
- Logic:
- Platinum
Customers who spend the most, purchase frequently, and explore many genres and artists, making them the most valuable customers.
- Gold
Customers with high spending and regular purchases, but slightly lower engagement than Platinum customers.
- Silver
Customers with moderate spending and purchase activity who have the potential to become loyal customers.
- Bronze
Customers with low spending or limited purchasing behavior who may need promotional offers to increase engagement.
#### Task 4 — Country Expansion Strategy
- Management wants to expand into new countries.
- Develop a Country Performance Score using multiple business metrics:
I calculated a Country Performance Score using multiple business metrics instead of only total revenue. The score considers revenue, customer count, average revenue per customer, average invoice value, and genre diversity. Finally, I ranked all countries using RANK() and recommended the top three countries with the highest performance scores for future business expansion.
- Finally recommend the top three countries for future expansion and explain your reasoning.
1- "USA"
2- "Canada"
3- "France"
### Concept Check
- Why are multiple CTEs preferred over one large nested query?
Multiple CTEs are preferred because nested queries become complex and difficult to read and understand. CTEs break the query into smaller, organized steps, making it easier to write, debug, and reuse intermediate results.
- When would you use a window function instead of GROUP BY?
When we want all rows after grouping them as well as we also want rank,indexes,ranking, row numbering, running totals, or averages along them so in that case we use window functions.
- Explain the difference between ROW_NUMBER(), RANK(), and DENSE_RANK().
ROW_NUMBER() assigns a unique row number to every row from 1 to n, even if there are duplicate values. RANK() assigns the same rank to equal values but skips the next rank (e.g., 1, 1, 3). DENSE_RANK() also assigns the same rank to equal values but does not skip the next rank (e.g., 1, 1, 2).
- What is conditional aggregation?
Conditional aggregation means applying aggregate functions like SUM(), COUNT(), or AVG() only on rows that satisfy a specific condition. It is usually done using CASE WHEN inside the aggregate function.
###### SELECT
######     SUM(CASE WHEN amount > 10 THEN amount ELSE 0 END) AS total
###### FROM payment;
- How does CASE WHEN improve analytical reporting?
CASE WHEN improves analytical reporting by allowing us to apply business rules and classify data into different categories using if-else conditions. It helps create meaningful reports such as customer segments, revenue categories, and performance labels without changing the original data.
- Why should SQL queries be broken into logical stages?
SQL queries should be broken into logical stages to make them easier to read, understand, debug, maintain, and reuse. It also follows real business logic, where each step solves one part of the problem before moving to the next.
- What makes a SQL query maintainable?
A SQL query is maintainable when it is well organized, uses meaningful aliases, structured CTEs, properly written subqueries, clear comments, and consistent formatting. This makes it easier to read, modify, debug, and reuse.





