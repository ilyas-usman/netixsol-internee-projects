------------------------------------------------------------------------------
-- ANALYTICS PIPELINE — AdventureWorks
-- Enterprise Analytics Hackathon — Final Submission
--
--
-- STAGE 1  Base Analytics       (raw tables read here, once each)
-- STAGE 2  Business Metrics     (revenue trends, product & salesperson performance)
-- STAGE 3  Customer Segmentation
-- STAGE 4  Regional Analysis
-- STAGE 5  Inventory & Purchasing
-- STAGE 6  Executive KPI Summary
-- STAGE 7  Advanced SQL Showcase (proof of CTEs, window fns, ranking, etc.)
-- STAGE 8  Dashboard Extractions (named datasets for the notebook/reports)
------------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS analytics;
-- Drops a table/view/materialized view regardless of what it currently is.
-- Makes every CREATE TABLE below safe to re-run at any time.
CREATE OR REPLACE FUNCTION analytics.drop_any(p_schema text, p_name text)
RETURNS void AS $fn$
DECLARE
    v_kind "char";
BEGIN
    SELECT c.relkind INTO v_kind
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = p_schema AND c.relname = p_name;

    IF v_kind IS NULL THEN RETURN;
    ELSIF v_kind = 'v' THEN EXECUTE format('DROP VIEW %I.%I CASCADE', p_schema, p_name);
    ELSIF v_kind = 'm' THEN EXECUTE format('DROP MATERIALIZED VIEW %I.%I CASCADE', p_schema, p_name);
    ELSE EXECUTE format('DROP TABLE %I.%I CASCADE', p_schema, p_name);
    END IF;
END;
$fn$ LANGUAGE plpgsql;
------------------------------------------------------------------------------
-- STAGE 1 — BASE ANALYTICS
-- 9 domains: Sales, Customer, Product, Employee, Territory, Vendor,
-- Inventory, Purchasing, Date. Raw tables touched exactly once each.
------------------------------------------------------------------------------
-- 1.1 Sales Analytics — the core fact table, one row per order line.
SELECT analytics.drop_any('analytics', 'sales_analytics');
CREATE TABLE analytics.sales_analytics AS
SELECT
    soh.salesorderid,
    soh.orderdate,
    soh.customerid,
    soh.salespersonid,
    soh.territoryid,
    sod.productid,
    p.name AS product_name,
    sod.orderqty,
    sod.unitprice,
    sod.unitpricediscount,
    (sod.orderqty * sod.unitprice) AS gross_sales,
    (sod.orderqty * sod.unitprice) - (sod.orderqty * sod.unitprice * sod.unitpricediscount) AS net_sales
FROM sales.salesorderheader soh
JOIN sales.salesorderdetail sod ON soh.salesorderid = sod.salesorderid
JOIN production.product p ON sod.productid = p.productid;

CREATE INDEX idx_sales_customerid    ON analytics.sales_analytics (customerid);
CREATE INDEX idx_sales_productid     ON analytics.sales_analytics (productid);
CREATE INDEX idx_sales_salespersonid ON analytics.sales_analytics (salespersonid);
CREATE INDEX idx_sales_territoryid   ON analytics.sales_analytics (territoryid);
CREATE INDEX idx_sales_orderdate     ON analytics.sales_analytics (orderdate);
-- 1.2 Customer Analytics — one row per customer, order/revenue summary.
SELECT analytics.drop_any('analytics', 'customer_analytics');
CREATE TABLE analytics.customer_analytics AS
SELECT
    c.customerid,
    COUNT(DISTINCT sa.salesorderid) AS total_orders,
    SUM(sa.net_sales)               AS total_revenue,
    AVG(sa.net_sales)               AS avg_order,
    COUNT(DISTINCT sa.productid)    AS unique_products
FROM sales.customer c
LEFT JOIN analytics.sales_analytics sa ON sa.customerid = c.customerid
GROUP BY c.customerid;

CREATE INDEX idx_customer_analytics_id ON analytics.customer_analytics (customerid);

-- 1.3 Product Analytics — one row per product: category, cost, price,
-- stock thresholds and lifetime sales, all in a single table.
SELECT analytics.drop_any('analytics', 'product_analytics');
CREATE TABLE analytics.product_analytics AS
WITH product_sales AS (
    SELECT productid, SUM(orderqty) AS units_sold, SUM(net_sales) AS revenue, AVG(unitprice) AS avg_price
    FROM analytics.sales_analytics
    GROUP BY productid
)
SELECT
    pr.productid,
    pr.name AS product_name,
    pc.name AS category_name,
    psc.name AS subcategory_name,
    pr.standardcost,
    pr.listprice,
    pr.safetystocklevel,
    pr.reorderpoint,
    COALESCE(ps.units_sold, 0) AS units_sold,
    COALESCE(ps.revenue, 0)    AS revenue,
    ps.avg_price
FROM production.product pr
LEFT JOIN production.productsubcategory psc ON psc.productsubcategoryid = pr.productsubcategoryid
LEFT JOIN production.productcategory pc     ON pc.productcategoryid = psc.productcategoryid
LEFT JOIN product_sales ps ON ps.productid = pr.productid;

CREATE INDEX idx_product_analytics_id ON analytics.product_analytics (productid);

-- 1.4 Employee Analytics — sales performance per salesperson.
SELECT analytics.drop_any('analytics', 'employee_analytics');
CREATE TABLE analytics.employee_analytics AS
SELECT
    salespersonid,
    COUNT(DISTINCT salesorderid) AS orders_completed,
    SUM(net_sales)               AS revenue,
    AVG(net_sales)               AS avg_sale
FROM analytics.sales_analytics
GROUP BY salespersonid;

CREATE INDEX idx_employee_analytics_id ON analytics.employee_analytics (salespersonid);

-- 1.5 Territory Analytics — revenue and customer count per territory.
SELECT analytics.drop_any('analytics', 'territory_analytics');
CREATE TABLE analytics.territory_analytics AS
SELECT
    t.territoryid,
    t.name,
    t.countryregioncode,
    SUM(sa.net_sales)             AS revenue,
    COUNT(DISTINCT sa.customerid) AS customers
FROM sales.salesterritory t
LEFT JOIN analytics.sales_analytics sa ON sa.territoryid = t.territoryid
GROUP BY t.territoryid, t.name, t.countryregioncode;

CREATE INDEX idx_territory_analytics_id ON analytics.territory_analytics (territoryid);

-- 1.6 Vendor Analytics — vendor master with product count.
SELECT analytics.drop_any('analytics', 'vendor_analytics');
CREATE TABLE analytics.vendor_analytics AS
SELECT
    v.businessentityid,
    v.name,
    COUNT(DISTINCT pv.productid) AS products_supplied
FROM purchasing.vendor v
JOIN purchasing.productvendor pv ON v.businessentityid = pv.businessentityid
GROUP BY v.businessentityid, v.name;

CREATE INDEX idx_vendor_analytics_id ON analytics.vendor_analytics (businessentityid);

-- 1.7 Inventory Analytics — stock level and health status per product.
SELECT analytics.drop_any('analytics', 'inventory_analytics');
CREATE TABLE analytics.inventory_analytics AS
WITH stock AS (
    SELECT productid, SUM(quantity) AS stock, COUNT(DISTINCT locationid) AS locations
    FROM production.productinventory
    GROUP BY productid
)
SELECT
    s.productid,
    pa.product_name,
    pa.category_name,
    s.stock,
    s.locations,
    pa.reorderpoint,
    pa.safetystocklevel,
    CASE
        WHEN s.stock = 0                            THEN 'Out of Stock'
        WHEN s.stock <= pa.reorderpoint              THEN 'Low Stock'
        WHEN s.stock > pa.safetystocklevel * 3       THEN 'Overstocked'
        ELSE 'Healthy'
    END AS stock_status
FROM stock s
LEFT JOIN analytics.product_analytics pa ON pa.productid = s.productid;

CREATE INDEX idx_inventory_analytics_id ON analytics.inventory_analytics (productid);

-- 1.8 Purchasing Analytics — one row per PO line: vendor, product, cost, quality.
SELECT analytics.drop_any('analytics', 'purchasing_analytics');
CREATE TABLE analytics.purchasing_analytics AS
SELECT
    poh.purchaseorderid,
    poh.orderdate,
    poh.vendorid,
    va.name AS vendor_name,
    pod.productid,
    pa.product_name,
    pod.orderqty,
    pod.unitprice,
    (pod.orderqty * pod.unitprice) AS linetotal,
    pod.rejectedqty,
    ROUND(pod.rejectedqty * 100.0 / NULLIF(pod.orderqty, 0), 2) AS reject_rate_pct
FROM purchasing.purchaseorderheader poh
JOIN purchasing.purchaseorderdetail pod ON pod.purchaseorderid = poh.purchaseorderid
LEFT JOIN analytics.vendor_analytics va  ON va.businessentityid = poh.vendorid
LEFT JOIN analytics.product_analytics pa ON pa.productid = pod.productid;

CREATE INDEX idx_purchasing_analytics_vendorid  ON analytics.purchasing_analytics (vendorid);
CREATE INDEX idx_purchasing_analytics_orderdate ON analytics.purchasing_analytics (orderdate);

-- 1.9 Date Analytics — monthly revenue calendar.
SELECT analytics.drop_any('analytics', 'date_analytics');
CREATE TABLE analytics.date_analytics AS
SELECT
    DATE_TRUNC('month', orderdate) AS sales_month,
    COUNT(*)       AS orders,
    SUM(net_sales) AS revenue
FROM analytics.sales_analytics
GROUP BY DATE_TRUNC('month', orderdate);

CREATE INDEX idx_date_analytics_month ON analytics.date_analytics (sales_month);

------------------------------------------------------------------------------
-- STAGE 2 — BUSINESS METRICS
-- Built only on Stage 1 tables.
------------------------------------------------------------------------------

-- 2.1 Monthly Revenue — trend, growth, moving average, running total.
SELECT analytics.drop_any('analytics', 'monthly_revenue');
CREATE TABLE analytics.monthly_revenue AS
SELECT
    sales_month,
    orders AS order_count,
    revenue,
    LAG(revenue) OVER (ORDER BY sales_month) AS prev_month_revenue,
    ROUND(CASE WHEN LAG(revenue) OVER (ORDER BY sales_month) > 0
        THEN ((revenue - LAG(revenue) OVER (ORDER BY sales_month)) / LAG(revenue) OVER (ORDER BY sales_month)) * 100
        ELSE NULL END, 2) AS mom_growth_pct,
    SUM(revenue) OVER (ORDER BY sales_month) AS cumulative_revenue,
    ROUND(AVG(revenue) OVER (ORDER BY sales_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS revenue_3mo_moving_avg
FROM analytics.date_analytics
ORDER BY sales_month;


-- 2.2 Quarterly Revenue — built from monthly_revenue.
SELECT analytics.drop_any('analytics', 'quarterly_revenue');
CREATE TABLE analytics.quarterly_revenue AS
WITH quarterly AS (
    SELECT DATE_TRUNC('quarter', sales_month) AS sales_quarter, SUM(revenue) AS revenue
    FROM analytics.monthly_revenue
    GROUP BY DATE_TRUNC('quarter', sales_month)
)
SELECT
    sales_quarter,
    revenue,
    LAG(revenue) OVER (ORDER BY sales_quarter) AS prev_quarter_revenue,
    ROUND(CASE WHEN LAG(revenue) OVER (ORDER BY sales_quarter) > 0
        THEN ((revenue - LAG(revenue) OVER (ORDER BY sales_quarter)) / LAG(revenue) OVER (ORDER BY sales_quarter)) * 100
        ELSE NULL END, 2) AS qoq_growth_pct
FROM quarterly
ORDER BY sales_quarter;


-- 2.3 Sales Growth (yearly) — built from quarterly_revenue.
SELECT analytics.drop_any('analytics', 'yearly_sales_growth');
CREATE TABLE analytics.yearly_sales_growth AS
WITH yearly AS (
    SELECT DATE_TRUNC('year', sales_quarter) AS sales_year, SUM(revenue) AS revenue
    FROM analytics.quarterly_revenue
    GROUP BY DATE_TRUNC('year', sales_quarter)
)
SELECT
    sales_year,
    revenue,
    LAG(revenue) OVER (ORDER BY sales_year) AS prev_year_revenue,
    ROUND(CASE WHEN LAG(revenue) OVER (ORDER BY sales_year) > 0
        THEN ((revenue - LAG(revenue) OVER (ORDER BY sales_year)) / LAG(revenue) OVER (ORDER BY sales_year)) * 100
        ELSE NULL END, 2) AS yoy_growth_pct
FROM yearly
ORDER BY sales_year;


-- 2.4 Product Performance — revenue, profit, margin and ranking in one table.
SELECT analytics.drop_any('analytics', 'product_performance');
CREATE TABLE analytics.product_performance AS
SELECT
    productid,
    product_name,
    category_name,
    subcategory_name,
    units_sold,
    revenue,
    ROUND(standardcost * units_sold, 2)            AS estimated_cost,
    ROUND(revenue - (standardcost * units_sold), 2) AS estimated_profit,
    ROUND(CASE WHEN revenue > 0
        THEN ((revenue - standardcost * units_sold) / revenue) * 100
        ELSE NULL END, 2) AS profit_margin_pct,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    RANK() OVER (ORDER BY (revenue - standardcost * units_sold) DESC) AS profit_rank,
    CASE
        WHEN RANK() OVER (ORDER BY revenue DESC) <= 10 THEN 'Top 10 Seller'
        WHEN RANK() OVER (ORDER BY revenue ASC)  <= 10 THEN 'Bottom 10 Seller'
        ELSE 'Mid Range'
    END AS performance_tier
FROM analytics.product_analytics;

CREATE INDEX idx_product_performance_id ON analytics.product_performance (productid);


-- 2.5 Salesperson Performance — ranking, revenue share, vs. team average.
SELECT analytics.drop_any('analytics', 'salesperson_performance');
CREATE TABLE analytics.salesperson_performance AS
WITH team AS (
    SELECT AVG(revenue) AS avg_revenue
    FROM analytics.employee_analytics
    WHERE salespersonid IS NOT NULL
)
SELECT
    e.salespersonid,
    e.orders_completed,
    e.revenue,
    e.avg_sale,
    RANK() OVER (ORDER BY e.revenue DESC) AS revenue_rank,
    ROUND(e.revenue * 100.0 / SUM(e.revenue) OVER (), 2) AS pct_of_total_revenue,
    t.avg_revenue AS team_avg_revenue,
    CASE
        WHEN e.revenue > t.avg_revenue * 1.1 THEN 'Above Average'
        WHEN e.revenue < t.avg_revenue * 0.9 THEN 'Below Average'
        ELSE 'At Average'
    END AS performance_category
FROM analytics.employee_analytics e
CROSS JOIN team t
WHERE e.salespersonid IS NOT NULL;


------------------------------------------------------------------------------
-- STAGE 3 — CUSTOMER SEGMENTATION
-- Built only on customer_analytics.
------------------------------------------------------------------------------
-- 3.1 Customer Segments — quartile-based classification.
SELECT analytics.drop_any('analytics', 'customer_segments');
CREATE TABLE analytics.customer_segments AS
WITH scored AS (
    SELECT
        customerid, total_orders, total_revenue, avg_order, unique_products,
        NTILE(4) OVER (ORDER BY total_revenue DESC NULLS LAST) AS revenue_quartile
    FROM analytics.customer_analytics
)
SELECT
    customerid, total_orders, total_revenue, avg_order, unique_products, revenue_quartile,
    CASE
        WHEN total_orders IS NULL OR total_orders = 0 THEN 'No Purchases'
        WHEN revenue_quartile = 1 AND total_orders > 1 THEN 'VIP'
        WHEN total_orders = 1                          THEN 'One-Time Buyer'
        WHEN revenue_quartile <= 2                      THEN 'Regular'
        ELSE 'Low Value'
    END AS customer_segment
FROM scored;

CREATE INDEX idx_customer_segments_id ON analytics.customer_segments (customerid);


-- 3.2 Customer Lifetime Value.
SELECT analytics.drop_any('analytics', 'customer_ltv');
CREATE TABLE analytics.customer_ltv AS
SELECT
    customerid,
    total_revenue AS lifetime_value,
    total_orders,
    avg_order AS avg_order_value,
    customer_segment,
    RANK() OVER (ORDER BY total_revenue DESC NULLS LAST) AS ltv_rank
FROM analytics.customer_segments;


-- 3.3 Customer Retention — repeat-purchase rate by segment.
SELECT analytics.drop_any('analytics', 'customer_retention');
CREATE TABLE analytics.customer_retention AS
SELECT
    customer_segment,
    COUNT(*) AS customer_count,
    COUNT(*) FILTER (WHERE total_orders > 1) AS repeat_customers,
    ROUND(COUNT(*) FILTER (WHERE total_orders > 1) * 100.0 / COUNT(*), 2) AS repeat_rate_pct,
    ROUND(AVG(total_orders), 2) AS avg_orders
FROM analytics.customer_segments
GROUP BY customer_segment;


-- 3.4 Repeat Customers — customer-level list (orders > 1).
SELECT analytics.drop_any('analytics', 'repeat_customers');
CREATE TABLE analytics.repeat_customers AS
SELECT customerid, total_orders, total_revenue, avg_order, unique_products, customer_segment
FROM analytics.customer_segments
WHERE total_orders > 1
ORDER BY total_orders DESC, total_revenue DESC;


------------------------------------------------------------------------------
-- STAGE 4 — REGIONAL ANALYSIS
-- Built only on territory_analytics and sales_analytics.
------------------------------------------------------------------------------
-- 4.1 Regional Performance — revenue, rank, tier per territory.
SELECT analytics.drop_any('analytics', 'regional_performance');
CREATE TABLE analytics.regional_performance AS
SELECT
    territoryid,
    name AS territory_name,
    countryregioncode,
    revenue,
    customers,
    RANK() OVER (ORDER BY revenue DESC NULLS LAST) AS revenue_rank,
    CASE
        WHEN RANK() OVER (ORDER BY revenue DESC NULLS LAST) <= 3 THEN 'Top Territory'
        WHEN RANK() OVER (ORDER BY revenue ASC NULLS LAST)  <= 3 THEN 'Lowest Territory'
        ELSE 'Mid Range'
    END AS territory_tier
FROM analytics.territory_analytics;

CREATE INDEX idx_regional_performance_id ON analytics.regional_performance (territoryid);


-- 4.2 Regional Monthly Trend — feeds regional_growth.
SELECT analytics.drop_any('analytics', 'regional_monthly_trend');
CREATE TABLE analytics.regional_monthly_trend AS
SELECT territoryid, DATE_TRUNC('month', orderdate) AS sales_month, SUM(net_sales) AS revenue
FROM analytics.sales_analytics
GROUP BY territoryid, DATE_TRUNC('month', orderdate);

CREATE INDEX idx_regional_trend_territoryid ON analytics.regional_monthly_trend (territoryid);


-- 4.3 Regional Growth — YoY per territory.
SELECT analytics.drop_any('analytics', 'regional_growth');
CREATE TABLE analytics.regional_growth AS
WITH yearly AS (
    SELECT territoryid, DATE_TRUNC('year', sales_month) AS sales_year, SUM(revenue) AS revenue
    FROM analytics.regional_monthly_trend
    GROUP BY territoryid, DATE_TRUNC('year', sales_month)
)
SELECT
    y.territoryid,
    rp.territory_name,
    y.sales_year,
    y.revenue,
    LAG(y.revenue) OVER (PARTITION BY y.territoryid ORDER BY y.sales_year) AS prev_year_revenue,
    ROUND(CASE WHEN LAG(y.revenue) OVER (PARTITION BY y.territoryid ORDER BY y.sales_year) > 0
        THEN ((y.revenue - LAG(y.revenue) OVER (PARTITION BY y.territoryid ORDER BY y.sales_year))
              / LAG(y.revenue) OVER (PARTITION BY y.territoryid ORDER BY y.sales_year)) * 100
        ELSE NULL END, 2) AS yoy_growth_pct
FROM yearly y
LEFT JOIN analytics.regional_performance rp ON rp.territoryid = y.territoryid
ORDER BY y.territoryid, y.sales_year;

------------------------------------------------------------------------------
-- STAGE 5 — INVENTORY & PURCHASING
-- Built only on inventory_analytics and purchasing_analytics.
------------------------------------------------------------------------------

-- 5.1 Products with Low Stock.
SELECT analytics.drop_any('analytics', 'low_stock_products');
CREATE TABLE analytics.low_stock_products AS
SELECT productid, product_name, category_name, stock, reorderpoint, stock_status
FROM analytics.inventory_analytics
WHERE stock_status IN ('Low Stock', 'Out of Stock')
ORDER BY stock ASC;


-- 5.2 Supplier Performance — spend and quality per vendor.
SELECT analytics.drop_any('analytics', 'supplier_performance');
CREATE TABLE analytics.supplier_performance AS
SELECT
    vendorid,
    vendor_name,
    COUNT(DISTINCT purchaseorderid) AS total_orders,
    SUM(orderqty)  AS total_units_ordered,
    SUM(linetotal) AS total_spend,
    ROUND(AVG(reject_rate_pct), 2) AS avg_reject_rate_pct,
    RANK() OVER (ORDER BY AVG(reject_rate_pct) ASC) AS quality_rank,
    RANK() OVER (ORDER BY SUM(linetotal) DESC) AS spend_rank
FROM analytics.purchasing_analytics
GROUP BY vendorid, vendor_name;


-- 5.3 Purchasing Trends — monthly spend with MoM growth.
SELECT analytics.drop_any('analytics', 'purchasing_trends');
CREATE TABLE analytics.purchasing_trends AS
WITH monthly AS (
    SELECT DATE_TRUNC('month', orderdate) AS purchase_month,
           COUNT(DISTINCT purchaseorderid) AS po_count,
           SUM(linetotal) AS total_spend
    FROM analytics.purchasing_analytics
    GROUP BY DATE_TRUNC('month', orderdate)
)
SELECT
    purchase_month, po_count, total_spend,
    LAG(total_spend) OVER (ORDER BY purchase_month) AS prev_month_spend,
    ROUND(CASE WHEN LAG(total_spend) OVER (ORDER BY purchase_month) > 0
        THEN ((total_spend - LAG(total_spend) OVER (ORDER BY purchase_month)) / LAG(total_spend) OVER (ORDER BY purchase_month)) * 100
        ELSE NULL END, 2) AS mom_spend_growth_pct
FROM monthly
ORDER BY purchase_month;

------------------------------------------------------------------------------
-- STAGE 6 — EXECUTIVE KPI SUMMARY
-- Reads only Stage 2-5 tables. Single-row dashboard scorecard.
------------------------------------------------------------------------------
SELECT analytics.drop_any('analytics', 'executive_kpi_dashboard');
CREATE TABLE analytics.executive_kpi_dashboard AS
SELECT
    (SELECT SUM(revenue) FROM analytics.monthly_revenue) AS total_revenue,
    (SELECT revenue FROM analytics.monthly_revenue ORDER BY sales_month DESC LIMIT 1) AS latest_month_revenue,
    (SELECT mom_growth_pct FROM analytics.monthly_revenue ORDER BY sales_month DESC LIMIT 1) AS latest_mom_growth_pct,
    (SELECT yoy_growth_pct FROM analytics.yearly_sales_growth ORDER BY sales_year DESC LIMIT 1) AS latest_yoy_growth_pct,
    (SELECT COUNT(*) FROM analytics.customer_segments) AS total_customers,
    (SELECT COUNT(*) FROM analytics.customer_segments WHERE customer_segment = 'VIP') AS vip_customers,
    (SELECT COUNT(*) FROM analytics.customer_segments WHERE customer_segment = 'No Purchases') AS inactive_customers,
    (SELECT ROUND(AVG(lifetime_value), 2) FROM analytics.customer_ltv) AS avg_customer_ltv,
    (SELECT product_name FROM analytics.product_performance ORDER BY revenue_rank LIMIT 1) AS top_product,
    (SELECT territory_name FROM analytics.regional_performance ORDER BY revenue_rank LIMIT 1) AS top_territory,
    (SELECT salespersonid FROM analytics.salesperson_performance ORDER BY revenue_rank LIMIT 1) AS top_salesperson_id,
    (SELECT COUNT(*) FROM analytics.regional_performance) AS total_territories,
    (SELECT COUNT(*) FROM analytics.low_stock_products) AS low_stock_product_count,
    (SELECT vendor_name FROM analytics.supplier_performance ORDER BY quality_rank LIMIT 1) AS best_vendor;

------------------------------------------------------------------------------
-- STAGE 7 — ADVANCED SQL SHOWCASE
-- One query demonstrating: chained CTEs, window functions, CASE WHEN,
-- conditional aggregation, ranking functions and complex joins together.
-- Reads only Stage 1-4 tables.
------------------------------------------------------------------------------
SELECT analytics.drop_any('analytics', 'advanced_sql_showcase');
CREATE TABLE analytics.advanced_sql_showcase AS
WITH base_sales AS (                                  -- CTE 1: complex join across 3 tables
    SELECT sa.territoryid, pa.category_name, sa.customerid, cs.customer_segment, sa.net_sales
    FROM analytics.sales_analytics sa
    JOIN analytics.product_analytics pa  ON pa.productid = sa.productid
    JOIN analytics.customer_segments cs  ON cs.customerid = sa.customerid
),
territory_category_agg AS (                            -- CTE 2: conditional aggregation
    SELECT
        territoryid, category_name,
        COUNT(DISTINCT customerid) AS customer_count,
        COUNT(DISTINCT customerid) FILTER (WHERE customer_segment = 'VIP') AS vip_customer_count,
        COUNT(DISTINCT customerid) FILTER (WHERE customer_segment = 'One-Time Buyer') AS one_time_buyer_count,
        SUM(net_sales) AS revenue
    FROM base_sales
    GROUP BY territoryid, category_name
),
ranked AS (                                              -- CTE 3: window & ranking functions
    SELECT
        territoryid, category_name, customer_count, vip_customer_count, one_time_buyer_count, revenue,
        RANK() OVER (PARTITION BY territoryid ORDER BY revenue DESC) AS rank_within_territory,
        RANK() OVER (ORDER BY revenue DESC) AS rank_overall,
        ROUND(revenue * 100.0 / SUM(revenue) OVER (PARTITION BY territoryid), 2) AS pct_of_territory_revenue
    FROM territory_category_agg
)
SELECT                                                    -- final: CASE WHEN + a 4th joined table
    r.territoryid, rp.territory_name, r.category_name, r.customer_count, r.vip_customer_count,
    r.one_time_buyer_count, r.revenue, r.rank_within_territory, r.rank_overall, r.pct_of_territory_revenue,
    CASE
        WHEN r.rank_within_territory = 1 AND r.pct_of_territory_revenue > 30 THEN 'Star Category'
        WHEN r.vip_customer_count > r.customer_count * 0.25 THEN 'VIP-Heavy'
        WHEN r.one_time_buyer_count > r.customer_count * 0.5 THEN 'Acquisition-Driven'
        ELSE 'Core'
    END AS category_classification
FROM ranked r
LEFT JOIN analytics.regional_performance rp ON rp.territoryid = r.territoryid
ORDER BY r.territoryid, r.rank_within_territory;

------------------------------------------------------------------------------
-- STAGE 8 — DASHBOARD EXTRACTIONS
-- Named datasets matching the brief exactly. Thin filters/rollups of Stage
-- 2/4 tables — no metric is ever recalculated.
------------------------------------------------------------------------------

SELECT analytics.drop_any('analytics', 'best_selling_products');
CREATE TABLE analytics.best_selling_products AS
SELECT productid, product_name, category_name, units_sold, revenue, revenue_rank, performance_tier
FROM analytics.product_performance
WHERE performance_tier = 'Top 10 Seller'
ORDER BY revenue_rank;

SELECT analytics.drop_any('analytics', 'lowest_performing_products');
CREATE TABLE analytics.lowest_performing_products AS
SELECT productid, product_name, category_name, units_sold, revenue, revenue_rank, performance_tier
FROM analytics.product_performance
WHERE performance_tier = 'Bottom 10 Seller'
ORDER BY revenue ASC;

SELECT analytics.drop_any('analytics', 'category_performance');
CREATE TABLE analytics.category_performance AS
SELECT
    category_name,
    SUM(units_sold) AS units_sold,
    SUM(revenue) AS revenue,
    SUM(estimated_profit) AS profit,
    ROUND(SUM(revenue) * 100.0 / SUM(SUM(revenue)) OVER (), 2) AS pct_of_total_revenue,
    RANK() OVER (ORDER BY SUM(revenue) DESC) AS category_rank
FROM analytics.product_performance
GROUP BY category_name;

SELECT analytics.drop_any('analytics', 'product_rankings');
CREATE TABLE analytics.product_rankings AS
SELECT productid, product_name, category_name, units_sold, revenue, estimated_profit, revenue_rank, profit_rank, performance_tier
FROM analytics.product_performance
ORDER BY revenue_rank;

SELECT analytics.drop_any('analytics', 'top_territories');
CREATE TABLE analytics.top_territories AS
SELECT territoryid, territory_name, revenue, customers, revenue_rank, territory_tier
FROM analytics.regional_performance
WHERE territory_tier = 'Top Territory'
ORDER BY revenue_rank;

SELECT analytics.drop_any('analytics', 'lowest_performing_territories');
CREATE TABLE analytics.lowest_performing_territories AS
SELECT territoryid, territory_name, revenue, customers, revenue_rank, territory_tier
FROM analytics.regional_performance
WHERE territory_tier = 'Lowest Territory'
ORDER BY revenue_rank DESC;

------------------------------------------------------------------------------
-- VERIFICATION — confirms every table exists and is populated.
------------------------------------------------------------------------------
SELECT 'Stage 1' AS stage, 'sales_analytics' AS table_name, COUNT(*) AS row_count FROM analytics.sales_analytics
UNION ALL SELECT 'Stage 1','customer_analytics',   COUNT(*) FROM analytics.customer_analytics
UNION ALL SELECT 'Stage 1','product_analytics',    COUNT(*) FROM analytics.product_analytics
UNION ALL SELECT 'Stage 1','employee_analytics',   COUNT(*) FROM analytics.employee_analytics
UNION ALL SELECT 'Stage 1','territory_analytics',  COUNT(*) FROM analytics.territory_analytics
UNION ALL SELECT 'Stage 1','vendor_analytics',     COUNT(*) FROM analytics.vendor_analytics
UNION ALL SELECT 'Stage 1','inventory_analytics',  COUNT(*) FROM analytics.inventory_analytics
UNION ALL SELECT 'Stage 1','purchasing_analytics', COUNT(*) FROM analytics.purchasing_analytics
UNION ALL SELECT 'Stage 1','date_analytics',       COUNT(*) FROM analytics.date_analytics
UNION ALL SELECT 'Stage 2','monthly_revenue',          COUNT(*) FROM analytics.monthly_revenue
UNION ALL SELECT 'Stage 2','quarterly_revenue',        COUNT(*) FROM analytics.quarterly_revenue
UNION ALL SELECT 'Stage 2','yearly_sales_growth',      COUNT(*) FROM analytics.yearly_sales_growth
UNION ALL SELECT 'Stage 2','product_performance',      COUNT(*) FROM analytics.product_performance
UNION ALL SELECT 'Stage 2','salesperson_performance',  COUNT(*) FROM analytics.salesperson_performance
UNION ALL SELECT 'Stage 3','customer_segments',   COUNT(*) FROM analytics.customer_segments
UNION ALL SELECT 'Stage 3','customer_ltv',        COUNT(*) FROM analytics.customer_ltv
UNION ALL SELECT 'Stage 3','customer_retention',  COUNT(*) FROM analytics.customer_retention
UNION ALL SELECT 'Stage 3','repeat_customers',    COUNT(*) FROM analytics.repeat_customers
UNION ALL SELECT 'Stage 4','regional_performance',     COUNT(*) FROM analytics.regional_performance
UNION ALL SELECT 'Stage 4','regional_monthly_trend',   COUNT(*) FROM analytics.regional_monthly_trend
UNION ALL SELECT 'Stage 4','regional_growth',          COUNT(*) FROM analytics.regional_growth
UNION ALL SELECT 'Stage 5','low_stock_products',    COUNT(*) FROM analytics.low_stock_products
UNION ALL SELECT 'Stage 5','supplier_performance',  COUNT(*) FROM analytics.supplier_performance
UNION ALL SELECT 'Stage 5','purchasing_trends',     COUNT(*) FROM analytics.purchasing_trends
UNION ALL SELECT 'Stage 6','executive_kpi_dashboard', COUNT(*) FROM analytics.executive_kpi_dashboard
UNION ALL SELECT 'Stage 7','advanced_sql_showcase',   COUNT(*) FROM analytics.advanced_sql_showcase
UNION ALL SELECT 'Stage 8','best_selling_products',            COUNT(*) FROM analytics.best_selling_products
UNION ALL SELECT 'Stage 8','lowest_performing_products',       COUNT(*) FROM analytics.lowest_performing_products
UNION ALL SELECT 'Stage 8','category_performance',             COUNT(*) FROM analytics.category_performance
UNION ALL SELECT 'Stage 8','product_rankings',                 COUNT(*) FROM analytics.product_rankings
UNION ALL SELECT 'Stage 8','top_territories',                  COUNT(*) FROM analytics.top_territories
UNION ALL SELECT 'Stage 8','lowest_performing_territories',    COUNT(*) FROM analytics.lowest_performing_territories
ORDER BY stage, table_name;

--Schema--
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'analytics'
ORDER BY table_name;