import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv(r"D:\Netixsol_Intern_Projects\Titanic-Dataset.csv")

sns.set_style("whitegrid")

# Line Chart 

survival_by_class = df.groupby("Pclass")["Survived"].mean()

plt.figure(figsize=(7,5))
plt.plot(survival_by_class.index,
         survival_by_class.values,
         marker="o",
         linewidth=2,
         label="Survival Rate")

plt.title("Survival Rate by Passenger Class")
plt.xlabel("Passenger Class")
plt.ylabel("Survival Rate")
plt.legend()
plt.grid(True)
plt.show()

print("Caption: Survival rate decreases as passenger class number increases.\n")

# Bar Chart 

avg_fare = df.groupby("Pclass")["Fare"].mean()

plt.figure(figsize=(7,5))
plt.bar(avg_fare.index.astype(str),
        avg_fare.values,
        color="orange",
        label="Average Fare")

plt.title("Average Fare by Passenger Class")
plt.xlabel("Passenger Class")
plt.ylabel("Average Fare")
plt.legend()
plt.grid(True)
plt.show()

print("Caption: First-class passengers paid the highest average fare.\n")

# Histogram 

plt.figure(figsize=(7,5))
plt.hist(df["Age"].dropna(),
         bins=20,
         color="skyblue",
         edgecolor="black",
         label="Age")

plt.title("Distribution of Passenger Ages")
plt.xlabel("Age")
plt.ylabel("Frequency")
plt.legend()
plt.grid(True)
plt.show()

print("Caption: Most passengers were young to middle-aged.\n")

# Box Plot

plt.figure(figsize=(7,5))
plt.boxplot(df["Fare"].dropna())

plt.title("Fare Distribution")
plt.ylabel("Fare")
plt.grid(True)
plt.show()

print("Caption: A few passengers paid much higher fares than others, indicating outliers.\n")

# Scatter Plot

plt.figure(figsize=(7,5))
plt.scatter(df["Age"],
            df["Fare"],
            color="green",
            label="Passengers")

plt.title("Age vs Fare")
plt.xlabel("Age")
plt.ylabel("Fare")
plt.legend()
plt.grid(True)
plt.show()

print("Caption: There is no strong linear relationship between Age and Fare.\n")

#  Heatmap 

plt.figure(figsize=(8,6))
sns.heatmap(df.corr(numeric_only=True),
            annot=True,
            cmap="coolwarm")

plt.title("Correlation Heatmap")
plt.show()

print("Caption: The heatmap shows the correlation among all numeric columns. Values near +1 or -1 indicate strong relationships.\n")