import joblib
import pandas as pd
import numpy as np
import shap

# ==========================================
# Load Saved Pipeline
# ==========================================
def create_features(X):

        X = X.copy()

        X["age_bucket"] = pd.cut(
            X["age"],
            bins=[0,30,50,100],
            labels=["Young","Adult","Senior"]
        )

        X["hours_bucket"] = pd.cut(
            X["hours-per-week"],
            bins=[0,35,45,100],
            labels=["Part-Time","Full-Time","Over-Time"]
        )

        X["capital_gain_flag"] = (
            X["capital-gain"] > 0
        ).astype(int)

        X["log_capital_gain"] = np.log1p(
            X["capital-gain"]
        )

        X["higher_education"] = (
            X["education-num"] >= 13
        ).astype(int)

        X["edu_hours"] = (
            X["education-num"] *
            X["hours-per-week"]
        )

        return X

model = joblib.load("D:\\Netixsol_Intern_Projects\\Week-4\\day5\\adult_income_pipeline.pkl")

# Original input columns
EXPECTED_COLUMNS = [
    "age",
    "workclass",
    "fnlwgt",
    "education",
    "education-num",
    "marital-status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "capital-gain",
    "capital-loss",
    "hours-per-week",
    "native-country"
]

# ==========================================
# Prediction Function
# ==========================================

def predict_income(raw_input):

    if isinstance(raw_input, dict):
        raw_input = pd.DataFrame([raw_input])

    elif isinstance(raw_input, str):
        raw_input = pd.read_csv(raw_input)

    # Input validation
    missing = [c for c in EXPECTED_COLUMNS if c not in raw_input.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    raw_input = raw_input[EXPECTED_COLUMNS]

    probability = model.predict_proba(raw_input)[:, 1]

    threshold = 0.50

    prediction = (probability >= threshold).astype(int)

    # SHAP explanation
    fe = model.named_steps["feature_engineering"].transform(raw_input)

    processed = model.named_steps["preprocessing"].transform(fe)

    rf = model.named_steps["classifier"]

    explainer = shap.TreeExplainer(rf)

    shap_values = explainer.shap_values(processed)

    feature_names = model.named_steps[
        "preprocessing"
    ].get_feature_names_out()

    contributions = pd.DataFrame({
        "Feature": feature_names,
        "Contribution": np.abs(shap_values[0, :, 1])
    })

    top3 = (
        contributions
        .sort_values("Contribution", ascending=False)
        .head(3)
    )

    return {
        "Probability": float(probability[0]),
        "Prediction": ">50K" if prediction[0] else "<=50K",
        "Top 3 Features": top3["Feature"].tolist()
    }
    


# ==========================================
# Basic Tests
# ==========================================

if __name__ == "__main__":

    print("=" * 60)
    print("TEST 1 - Valid Input")
    print("=" * 60)

    sample = {
        "age": 39,
        "workclass": "Private",
        "fnlwgt": 77516,
        "education": "Bachelors",
        "education-num": 13,
        "marital-status": "Never-married",
        "occupation": "Prof-specialty",
        "relationship": "Not-in-family",
        "race": "White",
        "sex": "Male",
        "capital-gain": 2174,
        "capital-loss": 0,
        "hours-per-week": 40,
        "native-country": "United-States"
    }

    print(predict_income(sample))

    print("\n" + "=" * 60)
    print("TEST 2 - Missing Column")
    print("=" * 60)

    bad = sample.copy()
    bad.pop("age")

    try:
        predict_income(bad)
    except Exception as e:
        print(e)

    print("\n" + "=" * 60)
    print("TEST 3 - Unseen Category")
    print("=" * 60)

    unseen = sample.copy()
    unseen["workclass"] = "Alien Company"

    print(predict_income(unseen))