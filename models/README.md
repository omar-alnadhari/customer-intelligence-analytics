# Generated model artifacts

Trained binary models are intentionally ignored by Git. Running the complete
pipeline recreates `churn_random_forest.joblib` in this directory during
notebook 05.

The saved bundle contains the fitted Random Forest, its ordered 28-feature
schema, the validation-selected threshold, and the 90-day prediction horizon.
Use the Python and package versions pinned by the repository when loading it.
