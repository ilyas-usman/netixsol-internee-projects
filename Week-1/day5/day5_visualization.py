import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv(r"D:\Netixsol_Intern_Projects\Titanic-Dataset.csv")

sns.set_style("whitegrid")

# Plot 1: Histogram

plt.figure(figsize=(8,5))
plt.hist(df["Age"].dropna(), bins=20, color="skyblue", edgecolor="black", label="Age")
plt.title("Distribution of Passenger Ages")
plt.xlabel("Age")
plt.ylabel("Frequency")
plt.legend()
plt.grid(True)
plt.show()
print("Histogram Interpretation:")
print("Most passengers are between young and middle age.\n")

# Plot 2: Bar Chart

avg_fare = df.groupby("Pclass")["Fare"].mean()
plt.figure(figsize=(8,5))
plt.bar(avg_fare.index.astype(str), avg_fare.values, color="orange", label="Average Fare")
plt.title("Average Fare by Passenger Class")
plt.xlabel("Passenger Class")
plt.ylabel("Average Fare")
plt.legend()
plt.grid(True)
plt.show()
print("Bar Chart Interpretation:")
print("Passengers in higher classes generally paid higher fares compared to lower classes.\n")

# Plot 3: Box Plot

plt.figure(figsize=(8,5))
plt.boxplot(df["Fare"].dropna())
plt.title("Fare Distribution with Outliers")
plt.ylabel("Fare")
plt.grid(True)
plt.show()

print("Box Plot Interpretation:")
print("The boxplot shows the spread of fares and highlights passengers with unusually high ticket prices as outliers.\n")

# Plot 4: Correlation Heatmap

plt.figure(figsize=(8,6))
sns.heatmap(df.corr(numeric_only=True), annot=True, cmap="coolwarm")
plt.title("Correlation Heatmap")
plt.show()
print("Heatmap Interpretation:")
print("The heatmap shows the correlation between numeric columns. Values closer to 1 or -1 indicate stronger relationships.\n")

# Plot 5: Scatter Plot

plt.figure(figsize=(8,5))
plt.scatter(df["Age"], df["Fare"], color="green", label="Passengers")
plt.title("Age vs Fare")
plt.xlabel("Age")
plt.ylabel("Fare")
plt.legend()
plt.grid(True)
plt.show()
print("Scatter Plot Interpretation:")
print("The scatter plot shows the relationship between passenger age and fare. No strong linear relationship is clearly visible.\n")