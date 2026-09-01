"""
Run this in your capstone folder (where Property_with_Feature_Engineering.csv
and dummy_commercial_properties.csv both live) to actually build the SQLite DB.

1. Copy structured_retrieval.py into this same folder first.
2. Copy dummy_commercial_properties.csv into this same folder too
   (or point COMMERCIAL_CSV at wherever you saved it).
3. pip install pandas
4. python run_build_db.py
"""
from structured_retrieval import build_database, query_properties, query_commercial, format_as_context

ZAMEEN_CSV = "Property_with_Feature_Engineering.csv"
COMMERCIAL_CSV = "dummy_commercial_properties.csv"

if __name__ == "__main__":
    build_database(ZAMEEN_CSV, COMMERCIAL_CSV)

    print("\n--- Sanity check: 3 bed houses in Lahore under 2 crore, for sale ---")
    results = query_properties(city="Lahore", purpose="For Sale", bedrooms=3,
                                max_price=20_000_000, limit=5)
    print(format_as_context(results, kind="residential"))

    print("\n--- Sanity check: commercial shops in Gulberg ---")
    c_results = query_commercial(city="Lahore", unit_type="Shop", limit=5)
    print(format_as_context(c_results, kind="commercial"))
