Week 2 Day 5 – AFL Match Context Integration

Relationship Discovery
Common Columns
Team
Opponent
Round
Year
Match Date
Merge Strategy

I used a composite key because a single column was not enough to identify a unique match.

Merge Keys:

team
opponent
round
year
match_date
Data Quality
Duplicate Records

Duplicate rows were checked and removed before merging.

Missing Values

Numeric missing values were filled using the median.

Text missing values were filled with Unknown.

Validation
Row count checked before and after merge.
Unmatched records checked.
Duplicate records checked after merge.
New columns verified.
Analysis
Home vs Away

Compared average fantasy points of players playing at home and away.

Crowd vs Fantasy Points

Checked whether larger crowds affect player fantasy points.

Venue Performance

Calculated average fantasy points for every venue.

Home/Away Records

Compared the number of player records for home and away matches.

Files Generated
enriched_round_stats.csv
final_enriched_dataset.csv
home_vs_away.csv
venue_performance.csv
context_summary.csv
Charts
1. Home vs Away Performance

Shows average fantasy points for home and away matches.

2. Crowd vs Fantasy Points

Shows the relationship between crowd attendance and fantasy points.

3. Top Venues

Shows which venues have the highest average fantasy points.

4. Home vs Away Records

Shows how many player records belong to home and away matches.

Conclusion

The player dataset was successfully enriched with match context. The merged dataset can now be used for deeper player performance analysis using venue, crowd attendance and home/away information.

