# Week 6 — Day 2: Prediction Models

## AFL Match Winner & Top Player Prediction

Machine Learning pipeline for predicting **AFL match winners** and **top-performing players**, developed for the **CM-IT Week 6 Day 2** project.

The project provides trained ML pipelines, evaluation notebooks, and reusable Python prediction functions that can later be exposed as tools for a **LangChain/LangGraph/Gemini agent**.

---

## 🎯 Objectives

* Build match-winner prediction models.
* Build top-player prediction models.
* Establish baseline models.
* Compare multiple ML algorithms.
* Evaluate models using appropriate metrics.
* Analyze feature importance.
* Check for potential data leakage.
* Save trained pipelines for reuse.
* Create a clean prediction API.
* Test predictions using random and invalid queries.
* Prepare models for future AI-agent integration.

---

## 📁 Project Structure

```text
Week-6/
└── day2/
    ├── dataset/
    │   ├── afl_players_info_raw.csv
    │   ├── afl_players_round_by_round_stats_raw.csv
    │   ├── afl_players_seasonal_stats_raw.csv
    │   ├── team_matches_home_away_raw (1).csv
    │   ├── team_ranking.csv
    │   ├── venue_performance.csv
    │   └── ...other datasets
    │
    ├── pipelines/
    │   ├── match_winner_pipeline.joblib
    │   ├── match_winner_gb.joblib
    │   ├── match_winner_lr.joblib
    │   ├── top_player_pipeline.joblib
    │   └── ...
    │
    ├── common.py
    ├── predict.py
    ├── train_models.py
    ├── Prediction-Models.ipynb
    └── README.md
```

All paths are **relative** to the `day2` directory.

```python
from pathlib import Path

DATA_DIR = Path("./dataset")
PIPELINE_DIR = Path("./pipelines")
```

No hardcoded machine-specific paths are required.

---

# 🧠 Models

## 1. Match Winner Prediction

The match prediction task is treated as a classification problem.

### Models

* Logistic Regression
* Gradient Boosting

### Features

The model uses engineered information such as:

* Recent team form
* Form difference
* Home/away information
* Matchup history
* Ranking information
* Venue performance
* Other pre-match features

### Evaluation

Models are evaluated using:

* Accuracy
* F1 Score
* ROC AUC
* Brier Score

Brier Score is included to evaluate the quality of predicted win probabilities.

Example:

```text
Team A → 72%
Team B → 28%
```

---

# 🏆 Top Player Prediction

The top-player task is formulated as a **regression + ranking** problem.

The model predicts an expected player performance score and then ranks players by their predicted score.

Example:

```text
Player A → 102.4
Player B → 97.8
Player C → 94.6
Player D → 91.2
Player E → 88.9
```

### Evaluation

* MAE
* RMSE
* Top-K Hit Rate

The Top-K metric checks whether the actual top performer appears within the model's predicted top-K players.

---

# 📊 Baselines

Simple baselines are established before training the ML models.

### Match Winner

Examples:

* Home-team baseline
* Higher-ranked-team baseline
* Majority-class baseline

### Top Player

Examples:

* Previous leader repeats
* Season-average leader
* Historical performance baseline

The ML models must provide meaningful improvement over these baselines.

---

# 🔍 Feature Importance & Sanity Checks

Feature importance is analyzed to determine whether the model relies on sensible football-related information.

Important features may include:

* Recent form
* Form margin
* Home advantage
* Matchup history
* Player recent performance
* Seasonal performance
* Venue performance

Potential leakage is also investigated.

Suspicious information includes:

* Final match scores
* Post-match statistics
* Future player performance
* Future ladder information
* Any information unavailable before prediction time

Rare categorical features are also checked for possible overfitting.

---

# 💾 Saved Pipelines

Trained models are stored in:

```text
./pipelines/
```

The pipeline directory is created automatically:

```python
from pathlib import Path

PIPELINE_DIR = Path("./pipelines")
PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
```

Saved pipelines can be loaded directly for inference without retraining.

This is important for future agent/tool integration.

---

# 🔮 Prediction API

Prediction functions are implemented in:

```text
predict.py
```

## Match Winner

```python
from predict import predict_match_winner

result = predict_match_winner(
    "Richmond Tigers",
    "Collingwood Magpies"
)

print(result)
```

The function returns information such as:

```text
Predicted winner
Home win probability
Away win probability
Team information
```

---

## Top Players

```python
from predict import predict_top_player

players = predict_top_player(
    team="Geelong Cats",
    top_n=5
)

print(players)
```

Returns a ranked list of predicted players.

Example:

```python
[
    {
        "player_id": 44960,
        "team": "Geelong Cats",
        "predicted_fantasy_points": 96.4,
        "rank": 1
    }
]
```

---

# ✅ Input Validation

The prediction API validates user inputs.

Examples:

```text
Unknown team
Invalid date
Date outside supported data range
Invalid top_n
Missing required input
```

Invalid inputs should produce clear `ValueError` messages instead of raw ML/pandas errors.

Example:

```text
ValueError: Unknown team: ABC Random Team
```

---

# 🧪 Testing

## Test Prediction Module

```powershell
python predict.py
```

This runs the example prediction calls.

---

## Randomized Testing

Random queries can be used to test the prediction API with different real teams.

```powershell
python test_predict.py
```

For reproducible results:

```powershell
python test_predict.py --seed 42
```

For larger testing:

```powershell
python test_predict.py --n-matches 20 --n-player-queries 10
```

### Random tests verify

**Match predictions**

* Valid team names
* Valid predicted winner
* Probability range
* Probability sum
* No NaN values
* No unexpected exceptions

**Player predictions**

* Valid teams
* Correct number of results
* Valid ranking
* Numeric predictions
* No duplicate players
* No NaN values

---

# ⚙️ Installation & Usage

## 1. Navigate to Day 2

```powershell
cd D:\Netixsol_Intern_Projects\Week-6\day2
```

## 2. Activate Virtual Environment

Example:

```powershell
.\.venv-1\Scripts\Activate.ps1
```

The terminal should show:

```text
(.venv-1)
```

## 3. Install Dependencies

```powershell
pip install pandas numpy scikit-learn joblib
```

## 4. Train Models

```powershell
python train_models.py
```

Trained artifacts will be saved to:

```text
./pipelines/
```

## 5. Run Predictions

```powershell
python predict.py
```

## 6. Run Random Tests

```powershell
python test_predict.py --seed 42
```

or:

```powershell
python test_predict.py --n-matches 20 --n-player-queries 10
```

---

# 📓 Notebook

The complete Day 2 analysis is available in:

```text
Prediction-Models.ipynb
```

The notebook covers:

```text
Data Loading
     ↓
Baselines
     ↓
Feature Preparation
     ↓
Model Training
     ↓
Evaluation
     ↓
Calibration
     ↓
Top Player Ranking
     ↓
Feature Importance
     ↓
Sanity Checks
     ↓
Pipeline Saving
```

Run the notebook from the `day2` directory so that relative paths work correctly.

---

# 🛠️ Technologies

* Python
* Pandas
* NumPy
* Scikit-learn
* Joblib
* Jupyter Notebook

### ML Techniques

* Classification
* Regression
* Logistic Regression
* Gradient Boosting
* Ridge Regression
* Feature Engineering
* Model Evaluation
* Probability Calibration
* Ranking
* Top-K Evaluation

---

# 🤖 Future Agent Integration

The prediction functions are designed to become callable AI-agent tools.

```text
User
 │
 ▼
AI Agent
 │
 ├── Match Winner Tool
 │       │
 │       ▼
 │  predict_match_winner()
 │
 └── Top Player Tool
         │
         ▼
    predict_top_player()
         │
         ▼
    Saved Pipelines
```

These functions can later be integrated with:

* LangChain
* LangGraph
* Gemini Function Calling
* Raw Python Agents

This provides the ML foundation for the upcoming agent/tool-calling tasks.

---

# 📌 Deliverables

* [x] Match winner baseline
* [x] Top player baseline
* [x] Match winner ML models
* [x] Top player regression model
* [x] Model evaluation
* [x] Calibration analysis
* [x] Feature importance
* [x] Leakage checks
* [x] Saved pipelines
* [x] `predict.py`
* [x] Input validation
* [x] Randomized testing
* [x] Jupyter notebook
* [x] Relative dataset paths
* [x] Future agent integration interface

---

# 📈 Project Workflow

```text
AFL Dataset
     ↓
Feature Engineering
     ↓
Baseline Models
     ↓
ML Model Training
     ↓
Model Evaluation
     ↓
Feature Importance & Sanity Checks
     ↓
Saved Pipelines
     ↓
Prediction API
     ↓
Randomized Testing
     ↓
AI Agent Tools
```

---

## Project Status

**Week 6 — Day 2: Completed ✅**

The project provides an end-to-end AFL prediction pipeline with reusable trained models and a clean Python inference interface ready for the next stage of agent integration.
