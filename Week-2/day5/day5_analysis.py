import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

output_folder = r"D:\Netixsol_Intern_Projects\Week-2\day5"
os.makedirs(output_folder, exist_ok=True)
# READ DATASETS
round_stats = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\Week-2\day5\afl_players_round_by_round_stats_raw.csv",
    low_memory=False
)

team_matches = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\Week-2\day5\team_matches_home_away_raw (1).csv",
    low_memory=False
)

print("=" * 60)
print("ROUND BY ROUND DATASET")
print("=" * 60)

print("\nShape")
print(round_stats.shape)

print("\nMissing Values")
print(round_stats.isnull().sum())

print("\nDuplicate Rows")
print(round_stats.duplicated().sum())


print("\n" + "=" * 60)
print("TEAM MATCH DATASET")
print("=" * 60)

print("\nShape")
print(team_matches.shape)

print("\nMissing Values")
print(team_matches.isnull().sum())

print("\nDuplicate Rows")
print(team_matches.duplicated().sum())


rows_before_round = len(round_stats)
rows_before_match = len(team_matches)
# REMOVE DUPLICATES

round_stats = round_stats.drop_duplicates()
team_matches = team_matches.drop_duplicates()

# HANDLE MISSING VALUES

for col in round_stats.columns:

    if pd.api.types.is_numeric_dtype(round_stats[col]):
        round_stats[col] = round_stats[col].fillna(round_stats[col].median())

    else:
        round_stats[col] = round_stats[col].fillna("Unknown")


for col in team_matches.columns:

    if pd.api.types.is_numeric_dtype(team_matches[col]):
        team_matches[col] = team_matches[col].fillna(team_matches[col].median())

    else:
        team_matches[col] = team_matches[col].fillna("Unknown")

# MAKE COMMON DATATYPES

round_stats["team"] = round_stats["team"].astype(str)
round_stats["opponent"] = round_stats["opponent"].astype(str)
round_stats["round"] = round_stats["round"].astype(str)
round_stats["year"] = round_stats["year"].astype(int)
round_stats["match_date"] = round_stats["match_date"].astype(str)

team_matches["team_name"] = team_matches["team_name"].astype(str)
team_matches["opponent"] = team_matches["opponent"].astype(str)
team_matches["round"] = team_matches["round"].astype(str)
team_matches["year"] = team_matches["year"].astype(int)
team_matches["match_date"] = team_matches["match_date"].astype(str)

# MERGE DATASETS

merged = pd.merge(

    round_stats,

    team_matches[
        [
            "team_name",
            "opponent",
            "round",
            "year",
            "match_date",
            "home_away",
            "venue",
            "crowd"
        ]
    ],

    left_on=[
        "team",
        "opponent",
        "round",
        "year",
        "match_date"
    ],

    right_on=[
        "team_name",
        "opponent",
        "round",
        "year",
        "match_date"
    ],

    how="left",
    indicator=True
)

# SAVE MERGED DATASET

merged.to_csv(
    os.path.join(output_folder, "enriched_round_stats.csv"),
    index=False
)

print("\nMerged Dataset Shape")
print(merged.shape)

print("\nEnriched dataset saved successfully.")

# PART 2 : MERGE VALIDATION

print("\n" + "=" * 60)
print("MERGE VALIDATION REPORT")
print("=" * 60)

# ROW COUNT VALIDATION

rows_after_merge = len(merged)

print("\nRow Count Validation")
print("------------------------------")
print("Round Stats Before Merge :", rows_before_round)
print("Merged Dataset Rows      :", rows_after_merge)

if rows_before_round == rows_after_merge:
    print("Row count is unchanged after merge.")
else:
    print("Row count changed after merge.")

# UNMATCHED RECORDS

unmatched = merged[merged["_merge"] == "left_only"]

print("\nUnmatched Records")
print("------------------------------")
print("Total Unmatched :", len(unmatched))

if len(unmatched) > 0:

    print(
        unmatched[
            [
                "team",
                "opponent",
                "round",
                "year",
                "match_date"
            ]
        ].head(10)
    )

    unmatched.to_csv(
        os.path.join(output_folder, "unmatched_records.csv"),
        index=False
    )

else:
    print("All records matched successfully.")

# DUPLICATE RECORDS AFTER MERGE


duplicate_records = merged.duplicated().sum()

print("\nDuplicate Records")
print("------------------------------")
print("Duplicate Rows :", duplicate_records)

if duplicate_records > 0:

    duplicates = merged[merged.duplicated()]

    duplicates.to_csv(
        os.path.join(output_folder, "duplicate_records_after_merge.csv"),
        index=False
    )

# NEW COLUMNS VALIDATION

print("\nContext Columns Validation")
print("------------------------------")

print("Missing Home/Away :", merged["home_away"].isnull().sum())
print("Missing Venue     :", merged["venue"].isnull().sum())
print("Missing Crowd     :", merged["crowd"].isnull().sum())

# MERGE SUMMARY
print("\nMerge Summary")
print("------------------------------")
print(merged["_merge"].value_counts())

# REMOVE HELPER COLUMN

merged.drop(columns="_merge", inplace=True)

# SAVE FINAL ENRICHED DATASET
merged.to_csv(
    os.path.join(output_folder, "enriched_round_stats.csv"),
    index=False
)

print("\nValidation Completed Successfully.")

print("\nFiles Generated")

print("enriched_round_stats.csv")

if len(unmatched) > 0:
    print("unmatched_records.csv")

if duplicate_records > 0:
    print("duplicate_records_after_merge.csv")
    
# CONTEXTUAL ANALYSIS
print("\n" + "=" * 60)
print("CONTEXTUAL ANALYSIS")
print("=" * 60)

# 1. HOME VS AWAY PERFORMANCE

home_away = merged.groupby("home_away").agg(

    Average_Fantasy=("fantasy_points", "mean"),
    Average_Score=("score", "mean"),
    Matches=("player_id", "count")

).reset_index()

print("\nHome vs Away Performance")
print(home_away)

home_away.to_csv(
    os.path.join(output_folder, "home_vs_away.csv"),
    index=False
)

plt.figure(figsize=(8,5))

sns.barplot(
    data=home_away,
    x="home_away",
    y="Average_Fantasy"
)

plt.title("Average Fantasy Points (Home vs Away)")
plt.xlabel("Home / Away")
plt.ylabel("Average Fantasy Points")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "1_home_vs_away.png")
)

plt.close()

# 2. CROWD VS FANTASY POINTS

plt.figure(figsize=(10,6))

sns.scatterplot(
    data=merged,
    x="crowd",
    y="fantasy_points"
)

plt.title("Crowd Size vs Fantasy Points")
plt.xlabel("Crowd")
plt.ylabel("Fantasy Points")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "2_crowd_vs_fantasy.png")
)

plt.close()

correlation = merged["crowd"].corr(
    merged["fantasy_points"]
)

print("\nCorrelation between Crowd and Fantasy Points")
print(correlation)

# 3. BEST VENUES

venue_stats = merged.groupby("venue").agg(

    Average_Fantasy=("fantasy_points", "mean"),
    Matches=("player_id", "count")

).reset_index()

venue_stats = venue_stats.sort_values(
    by="Average_Fantasy",
    ascending=False
)

print("\nTop Venues")
print(venue_stats.head(10))

venue_stats.to_csv(
    os.path.join(output_folder, "venue_performance.csv"),
    index=False
)

plt.figure(figsize=(12,6))

sns.barplot(
    data=venue_stats.head(10),
    x="Average_Fantasy",
    y="venue"
)

plt.title("Top 10 Venues by Average Fantasy Points")
plt.xlabel("Average Fantasy Points")
plt.ylabel("Venue")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "3_top_venues.png")
)

plt.close()

# 4. HOME / AWAY RECORD COUNT

plt.figure(figsize=(7,5))

sns.countplot(
    data=merged,
    x="home_away"
)

plt.title("Number of Player Records (Home vs Away)")
plt.xlabel("Home / Away")
plt.ylabel("Player Records")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "4_home_away_records.png")
)

plt.close()

# SUMMARY TABLE
summary = merged.groupby(
    ["home_away", "venue"]
).agg(

    Average_Fantasy=("fantasy_points", "mean"),
    Average_Score=("score", "mean"),
    Average_Crowd=("crowd", "mean"),
    Records=("player_id", "count")

).reset_index()

summary.to_csv(
    os.path.join(output_folder, "context_summary.csv"),
    index=False
)

print("\nContext Summary Created Successfully.")

print("\nFiles Generated")

print("home_vs_away.csv")
print("venue_performance.csv")
print("context_summary.csv")

print("\nCharts Generated")

print("1_home_vs_away.png")
print("2_crowd_vs_fantasy.png")
print("3_top_venues.png")
print("4_home_away_records.png")


print("\nMerge Keys Used")
print("---------------------------")
print("team")
print("opponent")
print("round")
print("year")
print("match_date")

print("\nReason")
print("---------------------------")
print("A single key was not enough because one team")
print("plays many matches every season.")
print("So multiple columns were used to identify")
print("each match correctly.")

print("\nChallenges")
print("---------------------------")
print("1. Missing values were present.")
print("2. Duplicate records existed.")
print("3. Same team appears many times.")
print("4. Composite key was required.")

print("\nAssumptions")
print("---------------------------")
print("1. Team + Opponent + Round + Year + Match Date")
print("   identify one match.")
print("2. Missing numeric values were filled using median.")
print("3. Missing text values were filled using 'Unknown'.")

# FINAL DATASET
merged.to_csv(
    os.path.join(output_folder, "final_enriched_dataset.csv"),
    index=False
)


print("\n" + "=" * 60)
print("FINAL SUMMARY")
print("=" * 60)

print("Original Round Records :", rows_before_round)
print("Merged Records         :", len(merged))
print("Columns in Dataset     :", merged.shape[1])

print("\nContext Columns Added")
print("---------------------------")
print("home_away")
print("venue")
print("crowd")

print("\n" + "=" * 60)
print("FILES GENERATED")
print("=" * 60)

files = [
    "enriched_round_stats.csv",
    "final_enriched_dataset.csv",
    "home_vs_away.csv",
    "venue_performance.csv",
    "context_summary.csv"
]

for file in files:
    print(file)

print("\nCharts Generated")

charts = [
    "1_home_vs_away.png",
    "2_crowd_vs_fantasy.png",
    "3_top_venues.png",
    "4_home_away_records.png"
]

for chart in charts:
    print(chart)

