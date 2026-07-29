import pandas as pd

df = pd.read_csv(r"D:\Netixsol_Intern_Projects\Titanic-Dataset.csv")

# First 5 rows of the dataset
print(df.head())

# Shape of the dataset
print(df.shape)

# Information about the dataset
print(df.info())

# Descriptive statistics of the dataset
print(df.describe())

# Q1: How many passengers are there in the dataset?
print("Q1:", len(df))

# Q2: How many passengers survived the Titanic disaster?
print("Q2:", df["Survived"].sum())

# Q3: How many passengers did not survive?
print("Q3:", len(df[df["Survived"] == 0]))

# Q4: What is the number of male and female passengers?
print("Q4:")
print(df["Sex"].value_counts())

# Q5: What is the average age of the passengers?
print("Q5:", df["Age"].mean())

# Q6: How many passengers belong to each passenger class?
print("Q6:")
print(df["Pclass"].value_counts().sort_index())

# Q7: What is the average fare paid by passengers in each class?
print("Q7:")
print(df.groupby("Pclass")["Fare"].mean())

# Q8: Which passenger paid the highest fare?
print("Q8:")
highest_fare = df["Fare"].max()
print(df[df["Fare"] == highest_fare][["Name", "Fare", "Pclass"]])