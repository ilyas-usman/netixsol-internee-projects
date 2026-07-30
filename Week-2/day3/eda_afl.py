import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

sns.set_style("whitegrid")
df = pd.read_csv(r"D:\Netixsol_Intern_Projects\merged_players.csv")
save_path = r"D:\Netixsol_Intern_Projects\Week-2\day3"
os.makedirs(save_path, exist_ok=True)

print("=" * 60)
print("EDA AFL PLAYER DATASET")
print("=" * 60)

print("\nBusiness Question 1")
print("Which teams have played the most games?")

team_games = df.groupby("team")["games_played"].sum().sort_values(ascending=False)
plt.figure(figsize=(10,6))
team_games.plot(kind="bar")
plt.title("Total Games Played by Team")
plt.xlabel("Team")
plt.ylabel("Total Games Played")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q1_Teams_Most_Games.png"))
plt.close()

print("Observations:")
print("- Some teams have played significantly more games.")
print("- Few teams have comparatively lower total games.")
print("Business Insight:")
print("- Teams with more games have larger performance history.\n")

print("=" * 60)

print("\nBusiness Question 2")
print("What is the distribution of player ages?")

plt.figure(figsize=(8,6))
plt.hist(df["last_age"].dropna(), bins=15)
plt.title("Distribution of Player Ages")
plt.xlabel("Age")
plt.ylabel("Number of Players")
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q2_Player_Age_Distribution.png"))
plt.close()

print("Observations:")
print("- Most players fall within the middle age range.")
print("- Very young and very old players are fewer.")
print("Business Insight:")
print("- Most AFL players are in their prime playing years.\n")

print("=" * 60)

print("\nBusiness Question 3")
print("Which teams have the highest number of players?")

player_count = df["player_teams"].value_counts().head(15)

plt.figure(figsize=(12,6))
player_count.plot(kind="bar")
plt.title("Top Teams by Number of Players")
plt.xlabel("Player Teams")
plt.ylabel("Number of Players")
plt.xticks(rotation=70)
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q3_Player_Teams_Count.png"))
plt.close()

print("Observations:")
print("- Some teams contribute more players.")
print("- Player distribution is uneven among teams.")
print("Business Insight:")
print("- Teams with more players have greater squad representation.\n")

print("=" * 60)

print("\nBusiness Question 4")
print("How does player weight vary across teams?")

top_teams = df["team"].value_counts().head(10).index

weight_df = df[df["team"].isin(top_teams)]

plt.figure(figsize=(12,6))
sns.boxplot(data=weight_df, x="team", y="weight")
plt.title("Player Weight by Team")
plt.xlabel("Team")
plt.ylabel("Weight")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q4_Player_Weight_Boxplot.png"))
plt.close()

print("Observations:")
print("- Weight varies between different teams.")
print("- Some teams have visible outliers.")
print("Business Insight:")
print("- Physical characteristics differ among teams.\n")

print("=" * 60)

print("\nBusiness Question 5")
print("Which teams have the highest average fantasy points?")

fantasy = df.groupby("team")["avg_fantasy_points"].mean().sort_values(ascending=False)

plt.figure(figsize=(10,6))
fantasy.plot(kind="bar")
plt.title("Average Fantasy Points by Team")
plt.xlabel("Team")
plt.ylabel("Average Fantasy Points")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q5_Average_Fantasy_Points.png"))
plt.close()

print("Observations:")
print("- Some teams have much higher fantasy scores.")
print("- Team performance differs noticeably.")
print("Business Insight:")
print("- Higher fantasy points indicate stronger player performance.\n")

print("=" * 60)

print("\nBusiness Question 6")
print("Who are the Top 15 Goal Scorers?")

top_goals = (
    df.groupby("player_name")["goals"]
    .sum()
    .sort_values(ascending=False)
    .head(15)
)

plt.figure(figsize=(10,7))
top_goals.sort_values().plot(kind="barh")
plt.title("Top 15 Goal Scorers")
plt.xlabel("Goals")
plt.ylabel("Player")
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q6_Top_15_Goal_Scorers.png"))
plt.close()

print("Observations:")
print("- Few players score considerably more goals.")
print("- Goal scoring decreases after the top players.")
print("Business Insight:")
print("- Top scorers contribute heavily to team success.\n")

print("=" * 60)

print("\nBusiness Question 7")
print("How many records are available for each season?")

season = df["year"].value_counts().sort_index()

plt.figure(figsize=(10,6))
season.plot(kind="bar")
plt.title("Records Available Per Season")
plt.xlabel("Season")
plt.ylabel("Number of Records")
plt.tight_layout()
plt.savefig(os.path.join(save_path, "Q7_Season_Records.png"))
plt.close()

print("Observations:")
print("- Some seasons have more records than others.")
print("- Record count changes over the years.")
print("Business Insight:")
print("- Seasons with more records provide richer analysis.\n")

print("=" * 60)
print("SUMMARY")
print("=" * 60)

print("1. Some teams have played more games than others.")
print("2. Most players belong to the middle-age group.")
print("3. Player representation varies across teams.")
print("4. Player weight differs among teams.")
print("5. Fantasy points vary by team.")
print("6. A few players dominate goal scoring.")
print("7. Record availability changes from season to season.")

print("\nCharts saved successfully in:")
print(save_path)