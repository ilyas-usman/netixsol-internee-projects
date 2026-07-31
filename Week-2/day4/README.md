# Week 2 Day 4 – AFL Player Performance Investigation

# Data Cleaning

Before starting the analysis I checked the datasets for:

- Missing values
- Duplicate rows
- Wrong data types

After checking:

- Duplicate rows were removed.
- Missing numeric values were filled using median.
- Missing text values were filled with "Unknown".
- Player IDs were converted into the same datatype before merging.

# Dataset Merge

I merged the datasets using:

- player_id from seasonal stats
- id from players info

This created one merged dataset for analysis.

# Feature Engineering

I created five new features to better measure player performance.

# Goals_Per_Game
Shows average goals scored in one game.

# Fantasy_Per_Game
Shows average fantasy points per game.

# Disposals_Per_Game
Shows average disposals in each game.

# Tackles_Per_Game
Shows average tackles in each game.

# Marks_Per_Game
Shows average marks in each game.

# Performance Index

I created my own Performance Index using these statistics:

- Fantasy Points
- Goals
- Disposals
- Tackles
- Marks
- Clearances

Fantasy points were given the highest weight because they already combine many important player actions.

Players were ranked according to this index.

# Charts

## 1. Top 10 Most Valuable Players

This chart shows the players with the highest Performance Index.

## 2. Most Consistent Players

This chart shows players with the lowest standard deviation in fantasy points.

Lower standard deviation means more consistent performance.

## 3. Top Improved Players

This chart compares the first game and last game fantasy points.

Players with positive improvement performed better at the end of the season.


## 4. Top Declined Players

This chart shows players whose fantasy points decreased during the season.

## 5. Performance Index Distribution

This histogram shows how player performance is spread across the dataset.

Most players are average while only a few have very high performance.


## 6. Top Goal Scorers

This chart shows the players who scored the most goals.

## 7. Team Performance

This chart ranks teams using the average Performance Index of their players.

## 8. Recommended Players

This chart shows the five best players recommended for recruitment.

These players have the highest Performance Index.

# Business Insights

### Insight 1

Only a small number of players achieved a very high Performance Index.

### Insight 2

Fantasy points are a strong indicator of overall player performance.

### Insight 3

Some players remained very consistent throughout the season.

### Insight 4

Several players improved their performance as the season progressed.

### Insight 5

Some players showed a clear decline during the season.

### Insight 6

A few teams had much stronger average player performance than others.

### Insight 7

Goal scoring alone is not enough to become the most valuable player.

### Insight 8

Players with better all-round statistics ranked higher.

### Insight 9

Feature engineering helped compare players more fairly.

### Insight 10

The Performance Index made it easier to rank players using multiple statistics instead of only one.

# Final Recommendations

Based on the Performance Index, I selected the top 5 players for recruitment.

These players have:

- High fantasy points
- Good goal scoring
- Strong disposals
- Good tackling ability
- Consistent overall performance

---

# Files Generated

## CSV Files

- merged_analysis_dataset.csv
- final_analysis_dataset.csv
- top10_players.csv
- most_consistent_players.csv
- improved_players.csv
- declined_players.csv
- team_ranking.csv
- recommended_players.csv

## Charts

- 1_top10_players.png
- 2_consistent_players.png
- 3_improved_players.png
- 4_declined_players.png
- 5_performance_distribution.png
- 6_top_goal_scorers.png
- 7_team_performance.png
- 8_recommended_players.png

# Conclusion

This analysis helped identify valuable, consistent and improving players by combining multiple performance statistics into a single Performance Index. The results can help in making better recruitment and team selection decisions.