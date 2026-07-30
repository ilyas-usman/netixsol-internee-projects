First I loaded both datasets.

Then I checked:

- Number of rows and columns
- Missing values
- Duplicate rows
- Data types of all columns

# Cleaning Done

- Removed duplicate rows.
- Filled missing numeric values with median.
- Filled missing text values with "Unknown".
- Converted numeric strings into numeric datatype where possible.

# Validation

After cleaning I checked:

- Rows before and after cleaning.
- Remaining missing values.
- Remaining duplicate rows.
- Matched and unmatched player IDs after merging.

# Merging

I merged both datasets using:

- `player_id` from seasonal_stats
- `id` from players_info

# Files Created

- cleaned_players_info.csv
- cleaned_seasonal_stats.csv
- merged_players.csv

# Observations

- Duplicate rows were removed.
- Missing values were handled.
- Both datasets were merged successfully.
- Some player IDs could not be matched.
- The final merged dataset is ready for analysis.