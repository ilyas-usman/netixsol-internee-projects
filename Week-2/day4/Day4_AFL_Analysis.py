import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

output_folder = r"D:\Netixsol_Intern_Projects\Week-2\day4"
os.makedirs(output_folder, exist_ok=True)

players_info = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\Week-2\day4\afl_players_info_raw.csv",
    low_memory=False
)

season_stats = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\Week-2\day4\afl_players_seasonal_stats_raw.csv",
    dtype={"player_id": str},
    low_memory=False
)

round_stats = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\Week-2\day4\afl_players_round_by_round_stats_raw.csv",
    dtype={"player_id": str},
    low_memory=False
)

print("=" * 60)
print("DATA QUALITY CHECK")
print("=" * 60)

print("\nPlayers Info Shape")
print(players_info.shape)

print("\nSeason Stats Shape")
print(season_stats.shape)

print("\nRound Stats Shape")
print(round_stats.shape)

print("\nMissing Values")
print(players_info.isnull().sum())
print(season_stats.isnull().sum())
print(round_stats.isnull().sum())

print("\nDuplicate Rows")
print("Players Info :", players_info.duplicated().sum())
print("Season Stats :", season_stats.duplicated().sum())
print("Round Stats  :", round_stats.duplicated().sum())

players_info = players_info.drop_duplicates()
season_stats = season_stats.drop_duplicates()
round_stats = round_stats.drop_duplicates()

for col in players_info.columns:
    if pd.api.types.is_numeric_dtype(players_info[col]):
        players_info[col] = players_info[col].fillna(players_info[col].median())
    else:
        players_info[col] = players_info[col].fillna("Unknown")

for col in season_stats.columns:
    if pd.api.types.is_numeric_dtype(season_stats[col]):
        season_stats[col] = season_stats[col].fillna(season_stats[col].median())
    else:
        season_stats[col] = season_stats[col].fillna("Unknown")

for col in round_stats.columns:
    if pd.api.types.is_numeric_dtype(round_stats[col]):
        round_stats[col] = round_stats[col].fillna(round_stats[col].median())
    else:
        round_stats[col] = round_stats[col].fillna("Unknown")

players_info["id"] = players_info["id"].astype(str)
season_stats["player_id"] = season_stats["player_id"].astype(str)
round_stats["player_id"] = round_stats["player_id"].astype(str)

merged = pd.merge(
    season_stats,
    players_info,
    left_on="player_id",
    right_on="id",
    how="left"
)

merged = merged[
    [
        "player_id",
        "player_name",
        "team",
        "year",
        "games_played",
        "last_age",
        "height",
        "weight",
        "goals",
        "kicks",
        "marks",
        "handballs",
        "disposals",
        "hit_outs",
        "tackles",
        "clearances",
        "contested_marks",
        "goal_assists",
        "brownlow_votes",
        "total_fantasy_points",
        "avg_fantasy_points",
        "avg_score"
    ]
]

merged["Goals_Per_Game"] = merged["goals"] / merged["games_played"]
merged["Fantasy_Per_Game"] = merged["total_fantasy_points"] / merged["games_played"]
merged["Disposals_Per_Game"] = merged["disposals"] / merged["games_played"]
merged["Tackles_Per_Game"] = merged["tackles"] / merged["games_played"]
merged["Marks_Per_Game"] = merged["marks"] / merged["games_played"]

merged = merged.replace([np.inf, -np.inf], np.nan)
merged = merged.fillna(0)

merged["Performance_Index"] = (
    merged["Fantasy_Per_Game"] * 0.35 +
    merged["Goals_Per_Game"] * 0.20 +
    merged["Disposals_Per_Game"] * 0.15 +
    merged["Tackles_Per_Game"] * 0.10 +
    merged["Marks_Per_Game"] * 0.10 +
    merged["clearances"] * 0.10
)

print("\nMerged Dataset Shape")
print(merged.shape)

merged.to_csv(
    os.path.join(output_folder, "merged_analysis_dataset.csv"),
    index=False
)

print("\nMerged dataset saved successfully.")

# TOP PLAYERS, CONSISTENCY & PERFORMANCE TRENDS

print("\n" + "=" * 60)
print("TOP 10 MOST VALUABLE PLAYERS")
print("=" * 60)

top10_players = merged.sort_values(
    by="Performance_Index",
    ascending=False
).head(10)

print(
    top10_players[
        [
            "player_name",
            "team",
            "Performance_Index",
            "Fantasy_Per_Game",
            "Goals_Per_Game"
        ]
    ]
)

top10_players.to_csv(
    os.path.join(output_folder, "top10_players.csv"),
    index=False
)

# Visualization 1 

plt.figure(figsize=(12,6))

sns.barplot(
    data=top10_players,
    x="Performance_Index",
    y="player_name"
)

plt.title("Top 10 Most Valuable Players")
plt.xlabel("Performance Index")
plt.ylabel("Player")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "1_top10_players.png")
)
plt.close()
# MOST CONSISTENT PLAYERS

print("\n" + "=" * 60)
print("MOST CONSISTENT PLAYERS")
print("=" * 60)

consistency = round_stats.groupby(
    "player_id"
).agg(

    player_name=("id","first"),

    avg_fantasy=("fantasy_points","mean"),

    std_fantasy=("fantasy_points","std"),

    matches=("fantasy_points","count")

).reset_index()

consistency["std_fantasy"] = consistency["std_fantasy"].fillna(0)

consistency = consistency[
    consistency["matches"] >= 5
]

consistency = consistency.sort_values(
    by="std_fantasy"
)

top_consistent = consistency.head(10)

print(top_consistent)

top_consistent.to_csv(
    os.path.join(output_folder,"most_consistent_players.csv"),
    index=False
)

# Visualization 2 
plt.figure(figsize=(12,6))

sns.barplot(
    data=top_consistent,
    x="std_fantasy",
    y="player_id"
)

plt.title("Most Consistent Players")
plt.xlabel("Fantasy Points Standard Deviation")
plt.ylabel("Player ID")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder,"2_consistent_players.png")
)

plt.close()

# PLAYER PERFORMANCE TREND

print("\n" + "=" * 60)
print("PERFORMANCE TREND")
print("=" * 60)

trend = round_stats.groupby(
    "player_id"
).agg(

    first_game=("fantasy_points","first"),

    last_game=("fantasy_points","last"),

    avg_fantasy=("fantasy_points","mean")

).reset_index()

trend["Improvement"] = (
    trend["last_game"] -
    trend["first_game"]
)

improved_players = trend.sort_values(
    by="Improvement",
    ascending=False
).head(10)

declined_players = trend.sort_values(
    by="Improvement"
).head(10)

print("\nTop Improved Players")

print(
    improved_players[
        [
            "player_id",
            "Improvement"
        ]
    ]
)

print("\nTop Declined Players")

print(
    declined_players[
        [
            "player_id",
            "Improvement"
        ]
    ]
)

improved_players.to_csv(
    os.path.join(output_folder,"improved_players.csv"),
    index=False
)

declined_players.to_csv(
    os.path.join(output_folder,"declined_players.csv"),
    index=False
)

# Visualization 3 

plt.figure(figsize=(12,6))

sns.barplot(
    data=improved_players,
    x="Improvement",
    y="player_id",
    color="green"
)

plt.title("Top Improved Players")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder,"3_improved_players.png")
)

plt.close()

# Visualization 4 

plt.figure(figsize=(12,6))

sns.barplot(
    data=declined_players,
    x="Improvement",
    y="player_id",
    color="red"
)

plt.title("Top Declined Players")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder,"4_declined_players.png")
)

plt.close()

# PLAYER PERFORMANCE DISTRIBUTION


plt.figure(figsize=(10,6))

sns.histplot(
    merged["Performance_Index"],
    bins=25,
    kde=True
)

plt.title("Performance Index Distribution")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder,"5_performance_distribution.png")
)

plt.close()

# TOP GOAL SCORERS

top_goals = merged.sort_values(
    by="goals",
    ascending=False
).head(10)

plt.figure(figsize=(12,6))

sns.barplot(
    data=top_goals,
    x="goals",
    y="player_name"
)

plt.title("Top Goal Scorers")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder,"6_top_goal_scorers.png")
)

plt.close()

print("\nPart 2 Completed Successfully.")

# TEAM ANALYSIS, RECOMMENDATIONS & FINAL OUTPUTS

print("\n" + "=" * 60)
print("TEAM PERFORMANCE ANALYSIS")
print("=" * 60)

team_ranking = merged.groupby("team").agg(
    Avg_Performance=("Performance_Index", "mean"),
    Avg_Fantasy=("Fantasy_Per_Game", "mean"),
    Avg_Goals=("Goals_Per_Game", "mean"),
    Avg_Disposals=("Disposals_Per_Game", "mean"),
    Players=("player_id", "count")
).reset_index()

team_ranking = team_ranking.sort_values(
    by="Avg_Performance",
    ascending=False
)

print(team_ranking)

team_ranking.to_csv(
    os.path.join(output_folder, "team_ranking.csv"),
    index=False
)

# Visualization 7
plt.figure(figsize=(14,6))

sns.barplot(
    data=team_ranking,
    x="team",
    y="Avg_Performance"
)

plt.xticks(rotation=90)

plt.title("Average Team Performance")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "7_team_performance.png")
)

plt.close()

# FINAL RECOMMENDATION

print("\n" + "=" * 60)
print("FINAL PLAYER RECOMMENDATIONS")
print("=" * 60)

recommend_players = merged.sort_values(
    by="Performance_Index",
    ascending=False
)

recommend_players = recommend_players.drop_duplicates(
    subset="player_id"
)

recommend_players = recommend_players.head(5)

print(
    recommend_players[
        [
            "player_name",
            "team",
            "Performance_Index",
            "Fantasy_Per_Game",
            "Goals_Per_Game"
        ]
    ]
)

recommend_players.to_csv(
    os.path.join(output_folder, "recommended_players.csv"),
    index=False
)

# Visualization 8

plt.figure(figsize=(10,6))

sns.barplot(
    data=recommend_players,
    x="Performance_Index",
    y="player_name"
)

plt.title("Top 5 Recommended Players")

plt.tight_layout()

plt.savefig(
    os.path.join(output_folder, "8_recommended_players.png")
)

plt.close()

# EXPORT FINAL DATASET

merged.to_csv(
    os.path.join(output_folder, "final_analysis_dataset.csv"),
    index=False
)

# SUMMARY
print("\n" + "=" * 60)
print("FILES GENERATED")
print("=" * 60)

print("merged_analysis_dataset.csv")
print("final_analysis_dataset.csv")
print("top10_players.csv")
print("most_consistent_players.csv")
print("improved_players.csv")
print("declined_players.csv")
print("team_ranking.csv")
print("recommended_players.csv")

print("\nCharts Saved")

print("1_top10_players.png")
print("2_consistent_players.png")
print("3_improved_players.png")
print("4_declined_players.png")
print("5_performance_distribution.png")
print("6_top_goal_scorers.png")
print("7_team_performance.png")
print("8_recommended_players.png")

print("\nProject Completed Successfully.")