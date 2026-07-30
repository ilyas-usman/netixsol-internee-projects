import pandas as pd

players_info = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\afl_players_info_raw.csv",
    low_memory=False
)

seasonal_stats = pd.read_csv(
    r"D:\Netixsol_Intern_Projects\afl_players_seasonal_stats_raw.csv",
    dtype={"player_id": str},
    low_memory=False
)

print("========== DATA QUALITY ASSESSMENT ==========\n")

print("Players Info Shape:", players_info.shape)
print("Seasonal Stats Shape:", seasonal_stats.shape)

print("\nPlayers Info Missing Values")
print(players_info.isnull().sum())

print("\nSeasonal Stats Missing Values")
print(seasonal_stats.isnull().sum())

print("\nPlayers Info Duplicate Rows:", players_info.duplicated().sum())
print("Seasonal Stats Duplicate Rows:", seasonal_stats.duplicated().sum())

print("\nPlayers Info Data Types")
print(players_info.dtypes)

print("\nSeasonal Stats Data Types")
print(seasonal_stats.dtypes)

rows_before_players = players_info.shape[0]
rows_before_stats = seasonal_stats.shape[0]

players_info = players_info.drop_duplicates()
seasonal_stats = seasonal_stats.drop_duplicates()

for col in players_info.columns:
    if pd.api.types.is_numeric_dtype(players_info[col]):
        players_info[col] = players_info[col].fillna(players_info[col].median())
    else:
        players_info[col] = players_info[col].fillna("Unknown")

for col in seasonal_stats.columns:
    if pd.api.types.is_numeric_dtype(seasonal_stats[col]):
        seasonal_stats[col] = seasonal_stats[col].fillna(seasonal_stats[col].median())
    else:
        seasonal_stats[col] = seasonal_stats[col].fillna("Unknown")

for col in players_info.columns:
    if not pd.api.types.is_numeric_dtype(players_info[col]):
        try:
            players_info[col] = pd.to_numeric(players_info[col])
        except:
            pass

for col in seasonal_stats.columns:
    if not pd.api.types.is_numeric_dtype(seasonal_stats[col]):
        try:
            seasonal_stats[col] = pd.to_numeric(seasonal_stats[col])
        except:
            pass

rows_after_players = players_info.shape[0]
rows_after_stats = seasonal_stats.shape[0]

players_info.to_csv(
    r"D:\Netixsol_Intern_Projects\cleaned_players_info.csv",
    index=False
)

seasonal_stats.to_csv(
    r"D:\Netixsol_Intern_Projects\cleaned_seasonal_stats.csv",
    index=False
)

players_info["id"] = players_info["id"].astype(str)
seasonal_stats["player_id"] = seasonal_stats["player_id"].astype(str)

merged = pd.merge(
    seasonal_stats,
    players_info,
    left_on="player_id",
    right_on="id",
    how="left",
    indicator=True
)

merged.to_csv(
    r"D:\Netixsol_Intern_Projects\merged_players.csv",
    index=False
)

print("\n========== CLEANING LOG ==========\n")

print("1. Removed duplicate rows.")
print("2. Filled missing numeric values using the median.")
print("3. Filled missing text values with 'Unknown'.")
print("4. Converted numeric strings to numeric type where possible.")
print("5. Merged datasets using player_id (seasonal_stats) and id (players_info).")

print("\n========== VALIDATION REPORT ==========\n")

print("Players Info Rows Before:", rows_before_players)
print("Players Info Rows After :", rows_after_players)

print("Seasonal Stats Rows Before:", rows_before_stats)
print("Seasonal Stats Rows After :", rows_after_stats)

print("\nRemaining Missing Values (Players Info)")
print(players_info.isnull().sum())

print("\nRemaining Missing Values (Seasonal Stats)")
print(seasonal_stats.isnull().sum())

print("\nDuplicate Rows Remaining (Players Info):", players_info.duplicated().sum())
print("Duplicate Rows Remaining (Seasonal Stats):", seasonal_stats.duplicated().sum())

print("\nMerge Summary")
print(merged["_merge"].value_counts())

print("\nUnmatched player_id Values")
print(merged.loc[merged["_merge"] != "both", "player_id"])

print("\n========== OBSERVATIONS ==========\n")

print("• Duplicate records were removed from both datasets.")
print("• Missing values were handled using median or 'Unknown'.")
print("• The datasets were successfully merged.")
print("• Any player_id listed above could not be matched with the players information dataset.")
print("• The merged dataset is now ready for analysis.")

print("\n========== FILES GENERATED ==========\n")

print("cleaned_players_info.csv")
print("cleaned_seasonal_stats.csv")
print("merged_players.csv")