import pandas as pd

df = pd.read_csv(r"D:\Netixsol_Intern_Projects\Titanic-Dataset.csv")

print("=ORIGINAL DATA=")
print(df.head())

print("\n=DATA INFO=")
print(df.info())

print("\n=MISSING VALUES=")
print(df.isnull().sum())

print("\n=HANDLING MISSING VALUES=")

df["Age"] = df["Age"].fillna(df["Age"].mean())

if "Embarked" in df.columns:
    df["Embarked"] = df["Embarked"].fillna(df["Embarked"].mode()[0])

if "Cabin" in df.columns:
    df = df.drop(columns=["Cabin"])

print(df.isnull().sum())

print("\n=DATA TYPES=")
print(df.dtypes)

print("\n=FIXING DATA TYPES=")

df["Age"] = df["Age"].astype(float)
df["Fare"] = df["Fare"].astype(float)

print(df.dtypes)

print("\n=DUPLICATES=")

print("Duplicate Rows Before:", df.duplicated().sum())

df = df.drop_duplicates()

print("Duplicate Rows After:", df.duplicated().sum())

print("\n=CREATING NEW COLUMNS=")

df["Age_Group"] = df["Age"].apply(
    lambda age: "Child" if age < 18 else "Adult"
)

df["Fare_With_Tax"] = df["Fare"] * 1.10

print(df[["Age", "Age_Group", "Fare", "Fare_With_Tax"]].head())

print("\n=SUMMARY TABLE (PIVOT TABLE)=")

summary = df.pivot_table(
    index="Sex",
    columns="Pclass",
    values="Fare",
    aggfunc="mean"
)

print(summary)

print("\n=SECOND DATAFRAME=")

class_labels = pd.DataFrame({
    "Pclass": [1, 2, 3],
    "Class_Name": [
        "First Class",
        "Second Class",
        "Third Class"
    ]
})

print(class_labels)

print("\n=MERGED DATA=")

merged_df = pd.merge(
    df,
    class_labels,
    on="Pclass",
    how="left"
)

print(
    merged_df[
        [
            "Name",
            "Pclass",
            "Class_Name",
            "Fare"
        ]
    ].head()
)

print("\n=FINAL DATA=")

print(merged_df.head())

print("\nFinal Shape:", merged_df.shape)