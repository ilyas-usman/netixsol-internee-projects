# Week 3 Day 5 Hackathon 

## Database Overview

This project uses the AdventureWorks PostgreSQL database. It contains sales, customers, products, employees, territories, inventory, vendors, and purchasing data. The goal is to convert operational data into reusable analytical datasets for reporting and dashboards.


# Analytics Architecture

The project follows a layered analytics pipeline instead of writing separate SQL queries.

Raw Operational Tables
        ↓
Analytics Layer
        ↓
Business Metrics
        ↓
Customer Segmentation
        ↓
Regional Analysis
        ↓
Executive KPI Tables
        ↓
Python Dashboard
```

Each layer uses the output of the previous layer, making the solution reusable and easy to maintain.


# Intermediate Tables Created

## Task 1 – Analytics Layer

- sales_analytics
- customer_analytics
- product_analytics
- employee_analytics
- territory_analytics
- inventory_analytics
- vendor_analytics
- purchasing_analytics
- date_analytics
- executive_kpi

## Task 2 – Business Pipeline

- monthly_revenue
- quarterly_revenue
- yearly_sales_growth
- product_performance
- salesperson_performance
- customer_segments
- customer_ltv
- customer_retention
- regional_performance
- regional_monthly_trend
- regional_growth
- executive_kpi_dashboard

## Task 3 – Dashboard Datasets

- best_selling_products
- lowest_performing_products
- repeat_customers
- product_profitability
- category_performance
- product_rankings
- salesperson_revenue_contribution
- salesperson_performance_comparison
- top_territories
- lowest_performing_territories
- inventory_health
- low_stock_products
- supplier_performance
- purchasing_trends

---

# SQL Design Decisions

- Created a separate **analytics** schema to keep reporting tables organized.
- Built the pipeline in stages so every stage reuses previous outputs.
- Used analytical tables instead of querying raw tables repeatedly.
- Used CTEs to improve readability.
- Used indexes on important columns to improve query performance.
- Created reusable KPI tables for Python visualizations.

---

# Challenges Faced

- Setting up the AdventureWorks PostgreSQL database.
- Fixing PostgreSQL connection and database issues.
- Building the dependency chain without repeating calculations.
- Managing relationships across multiple business domains.
- Designing reusable datasets for future dashboards.

---

# Assumptions Made

- Standard Cost was used to estimate product profitability.
- Revenue was calculated after applying unit price discounts.
- Customer Lifetime Value was based on total revenue generated.
- Inventory health was determined using reorder point and safety stock level.
- Dashboard visualizations read only from analytical tables and not from raw operational tables.