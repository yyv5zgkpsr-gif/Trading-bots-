"""Thin wrapper around a scikit-learn classifier that predicts a direction
label (1=BUY, -1=SELL, 0=HOLD) and turns its class probabilities into a
single -1..1 conviction score, so it drops into agents/debate.py's
CONVICTION_THRESHOLD gate exactly like the rule-based technical score does.
"""

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from ml.features import FEATURE_COLUMNS


class DirectionModel:
    def __init__(self, classifier=None):
        self.classifier = classifier or RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=20, random_state=0
        )
        self.feature_columns = list(FEATURE_COLUMNS)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.classifier.fit(X[self.feature_columns], y)

    def predict_conviction(self, X: pd.DataFrame) -> pd.Series:
        """P(BUY) - P(SELL) per row, in [-1, 1]. A class the model never saw
        during training (e.g. it never predicted SELL) is treated as
        probability 0 for that class rather than erroring."""
        proba = self.classifier.predict_proba(X[self.feature_columns])
        classes = list(self.classifier.classes_)
        buy_p = proba[:, classes.index(1)] if 1 in classes else 0.0
        sell_p = proba[:, classes.index(-1)] if -1 in classes else 0.0
        return pd.Series(buy_p - sell_p, index=X.index)

    def save(self, path) -> None:
        joblib.dump({"classifier": self.classifier, "feature_columns": self.feature_columns}, path)

    @classmethod
    def load(cls, path) -> "DirectionModel":
        data = joblib.load(path)
        model = cls(classifier=data["classifier"])
        model.feature_columns = data["feature_columns"]
        return model
