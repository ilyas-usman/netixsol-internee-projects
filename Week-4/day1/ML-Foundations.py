# ============================
# Task 1: Problem Definition & Success Metric
import matplotlib
matplotlib.use("TkAgg")
import pandas as pd
from sklearn.datasets import fetch_openml
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    ConfusionMatrixDisplay
)

# Load Adult Dataset
adult = fetch_openml(name="adult", version=2, as_frame=True)
df = adult.frame

# Display first 5 rows
print("First 5 Rows:")
print(df.head())

# Check column names
print("\nColumns:")
print(df.columns)

# Convert target column to binary (0 = <=50K, 1 = >50K)
df["class"] = df["class"].map({
    "<=50K": 0,
    ">50K": 1
})

# Convert category to integer
df["class"] = df["class"].astype(int)
# Define target
target = "class"

print("\nTarget Variable:", target)
print("Positive Class (1): Income >50K")
print("Negative Class (0): Income <=50K")

# Calculate class counts
class_counts = df[target].value_counts()

print("\nClass Counts:")
print(class_counts)

# Calculate class base rate
positive_rate = df[target].mean() * 100
negative_rate = 100 - positive_rate

print(f"\nPositive Class Rate (>50K): {positive_rate:.2f}%")
print(f"Negative Class Rate (<=50K): {negative_rate:.2f}%")

# Business Objective
business_objective = (
    "Identify customers who are likely to earn more than $50K per year "
    "so that marketing campaigns target high-income customers and avoid "
    "wasting resources on low-income customers."
)

print("\nBusiness Objective:")
print(business_objective)

# Selected Evaluation Metric
primary_metric = "Precision"

print("\nPrimary Evaluation Metric:", primary_metric)

metric_reason = (
    "Precision is selected because false positives increase marketing costs. "
    "If the model predicts someone as high-income when they are not, "
    "the company wastes money on unnecessary marketing."
)

print("\nReason for Choosing Precision:")
print(metric_reason)

# Non-Technical Explanation
print("\nNon-Technical Explanation:")
print(
    "Our goal is to identify customers who are most likely to earn more than $50K per year. "
    "This helps the company focus marketing efforts on the right people while reducing unnecessary costs. "
    "Precision is used to make sure that most customers predicted as high-income are actually high-income."
)

# ==========================================================
# Task 2: Data Load & Quick Exploratory Data Analysis (EDA)
# ==========================
# 3. Clean Missing Values
# Replace '?' with NaN
df.replace("?", np.nan, inplace=True)

print("\nMissing Values in Each Column")
print(df.isnull().sum())

print("\nTarget Class Counts")
print(df["class"].value_counts())

# ==========================
# 5. Dataset Shape

print("\nDataset Shape")
print(df.shape)

# ==========================
# 6. Column Data Types

print("\nColumn Data Types")
print(df.dtypes)

# ==========================
# 7. Numeric Summary

print("\nNumeric Summary")
print(df.describe())

# ==========================
# 8. Categorical Value Counts

categorical_columns = df.select_dtypes(include=["object", "category"]).columns

print("\nCategorical Columns")
print(categorical_columns)

for column in categorical_columns:
    print(f"\nValue Counts for {column}")
    print(df[column].value_counts())
# ==========================
# 9. Histograms for Numeric Features

numeric_columns = df.select_dtypes(include=["int64", "float64"]).columns

df[numeric_columns].hist(figsize=(12, 8))

plt.suptitle("Histograms of Numeric Features")

plt.tight_layout()

plt.show()

# ==========================
# 10. Bar Plots for Categorical Features

for column in categorical_columns:

    plt.figure(figsize=(8, 4))

    df[column].value_counts().plot(kind="bar")

    plt.title(f"{column} Distribution")

    plt.xlabel(column)

    plt.ylabel("Count")

    plt.xticks(rotation=45)

    plt.tight_layout()

    plt.show()

# ==========================
# 11. Summary Table


summary_table = pd.DataFrame({
    "Count": df["class"].value_counts(),
    "Percentage": (df["class"].value_counts(normalize=True) * 100).round(2)
})

print("\nClass Distribution Summary")
print(summary_table)
# ==========================
# 12. Manual Observations
print("\nObservations:")
print("1. Most individuals work around 40 hours per week.")
print("2. Most individuals have zero capital gain.")
print("3. The Private workclass contains the highest number of people.")

# ==========================================================
# Task 3: Create Reproducible Train/Test Split
# -----------------------------
# 1. Separate Features & Target

X = df.drop("class", axis=1)
y = df["class"]
print("Features Shape:", X.shape)
print("Target Shape:", y.shape)

# -----------------------------
# 2. Create Hold-Out Test Set (80% Train, 20% Test)

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    stratify=y,
    random_state=42
)

print("\nTrain/Test Split")
print("X_train:", X_train.shape)
print("X_test :", X_test.shape)
print("y_train:", y_train.shape)
print("y_test :", y_test.shape)

# -----------------------------
# 3. Check Class Distribution

print("\nTraining Target Distribution")
print(y_train.value_counts(normalize=True) * 100)
print("\nTesting Target Distribution")
print(y_test.value_counts(normalize=True) * 100)

# -----------------------------
# 4. Optional Development Set

X_train, X_dev, y_train, y_dev = train_test_split(
    X_train,
    y_train,
    test_size=0.125,      
    stratify=y_train,
    random_state=42
)

print("\nFinal Dataset Split")
print("Training Set :", X_train.shape)
print("Development Set :", X_dev.shape)
print("Testing Set :", X_test.shape)
print("\nTarget Distribution")
print("Train")
print(y_train.value_counts(normalize=True) * 100)
print("\nDevelopment")
print(y_dev.value_counts(normalize=True) * 100)
print("\nTest")
print(y_test.value_counts(normalize=True) * 100)


# ==========================================================
# Task 4: Implement Simple Baselines
# ==========================================================
# ----------------------------------------------------------
# Baseline 1: Majority-Class Predictor

dummy = DummyClassifier(strategy="most_frequent")
dummy.fit(X_train, y_train)
dummy_predictions = dummy.predict(X_test)
print("\nMajority Class Predictions")
print(dummy_predictions[:20])
# ----------------------------------------------------------
# Baseline 2: Rule-Based Classifier
# Rule: education-num >= 13
rule_predictions = (X_test["education-num"] >= 13).astype(int)
print("\nRule-Based Predictions")
print(rule_predictions.head())

# ----------------------------------------------------------
# Metrics for Majority-Class Baseline
dummy_accuracy = accuracy_score(y_test, dummy_predictions)
dummy_precision = precision_score(
    y_test,
    dummy_predictions,
    zero_division=0
)

dummy_recall = recall_score(
    y_test,
    dummy_predictions,
    zero_division=0
)

dummy_f1 = f1_score(
    y_test,
    dummy_predictions,
    zero_division=0
)

dummy_roc = roc_auc_score(
    y_test,
    dummy_predictions
)

dummy_pr = average_precision_score(
    y_test,
    dummy_predictions
)

# ----------------------------------------------------------
# Metrics for Rule-Based Baseline

rule_accuracy = accuracy_score(
    y_test,
    rule_predictions
)

rule_precision = precision_score(
    y_test,
    rule_predictions,
    zero_division=0
)

rule_recall = recall_score(
    y_test,
    rule_predictions,
    zero_division=0
)

rule_f1 = f1_score(
    y_test,
    rule_predictions,
    zero_division=0
)

rule_roc = roc_auc_score(
    y_test,
    rule_predictions
)

rule_pr = average_precision_score(
    y_test,
    rule_predictions
)

# ----------------------------------------------------------
# Metrics Comparison Table
results = pd.DataFrame({

    "Metric":[
        "Accuracy",
        "Precision",
        "Recall",
        "F1 Score",
        "ROC AUC",
        "PR AUC"
    ],

    "Majority Baseline":[
        dummy_accuracy,
        dummy_precision,
        dummy_recall,
        dummy_f1,
        dummy_roc,
        dummy_pr
    ],

    "Rule Baseline":[
        rule_accuracy,
        rule_precision,
        rule_recall,
        rule_f1,
        rule_roc,
        rule_pr
    ]

})

print("\nBaseline Comparison")
print(results)

# ----------------------------------------------------------
# Confusion Matrix - Majority Baseline

cm = confusion_matrix(
    y_test,
    dummy_predictions
)

ConfusionMatrixDisplay(cm).plot()

plt.title("Majority Baseline")

plt.show()


# ----------------------------------------------------------
# Confusion Matrix - Rule Baseline

cm = confusion_matrix(
    y_test,
    rule_predictions
)

ConfusionMatrixDisplay(cm).plot()

plt.title("Rule-Based Baseline")

plt.show()

# ----------------------------------------------------------
# Interpretation
print("\nInterpretation")
print(
    "The rule-based classifier uses education level to identify high-income individuals, "
    "while the majority baseline predicts the same class for everyone."
)
print(
    "The rule-based baseline is expected to perform better because it uses useful information "
    "instead of always predicting the majority class."
)
print(
    "A good machine learning model should achieve higher Precision and F1 Score than these baselines."
)

# ==========================================================
# Task 5: Initial Error Analysis & Next Steps
# ----------------------------------------------------------
# 1. Create Results DataFrame

test_results = X_test.copy()

test_results["Actual"] = y_test.values
test_results["Predicted"] = rule_predictions.values
# ---------------------------------------------------------
# 2. Find False Positives
# Actual = 0, Predicted = 1
false_positives = test_results[
    (test_results["Actual"] == 0) &
    (test_results["Predicted"] == 1)
]

print("\nFirst 10 False Positives")
print(false_positives.head(10))

print("\nRandom 10 False Positives")
print(false_positives.sample(10, random_state=42))

print("\nTotal False Positives:")
print(len(false_positives))

# ----------------------------------------------------------
# 3. Find False Negatives
# Actual = 1, Predicted = 0

false_negatives = test_results[
    (test_results["Actual"] == 1) &
    (test_results["Predicted"] == 0)
]

print("\nFirst 10 False Negatives")
print(false_negatives.head(10))

print("\nRandom 10 False Negatives")
print(false_negatives.sample(10, random_state=42))

print("\nTotal False Negatives:")
print(len(false_negatives))
# ----------------------------------------------------------
# 4. Error Analysis

print("\nFalse Positive Summary")
print(false_positives.describe())

print("\nFalse Negative Summary")
print(false_negatives.describe())

print("\nEducation Distribution (False Positives)")
print(false_positives["education"].value_counts())

print("\nEducation Distribution (False Negatives)")
print(false_negatives["education"].value_counts())

print("\nHours Per Week Summary (False Positives)")
print(false_positives["hours-per-week"].describe())

print("\nHours Per Week Summary (False Negatives)")
print(false_negatives["hours-per-week"].describe())

# ----------------------------------------------------------
# 5. Next Steps

print("\nSuggested Improvements:")
print("1. Handle missing values in workclass, occupation, and native-country.")
print("2. Encode categorical features using One-Hot Encoding.")
print("3. Scale numeric features if required.")
print("4. Handle skewed features like capital-gain and capital-loss.")
print("5. Try better ML models such as Logistic Regression or Decision Tree.")
print("6. Perform feature engineering to improve prediction performance.")

# ----------------------------------------------------------
# 6. Primary Metric for Next Iteration
print("\nPrimary Metric for the Week:")
print(
    "Precision will remain the primary evaluation metric because "
    "the business wants to reduce unnecessary marketing costs. "
    "Future machine learning models should achieve higher Precision "
    "and F1 Score than the current baseline models while maintaining "
    "a reasonable Recall."
)