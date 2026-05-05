import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from typing import Any, List, Tuple


def create_training_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", RandomForestClassifier(n_estimators=150, random_state=42))
        ]
    )


def train_model(X: List[List[float]], y: List[int]) -> Tuple[Pipeline, float]:
    if not X or not y:
        raise ValueError("Training data must not be empty")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.18, random_state=42)
    pipeline = create_training_pipeline()
    pipeline.fit(X_train, y_train)
    score = pipeline.score(X_test, y_test)
    return pipeline, score


def save_model(pipeline: Pipeline, path: str = "model.joblib") -> None:
    joblib.dump(pipeline, path)


def load_model(path: str = "model.joblib") -> Any:
    return joblib.load(path)


def predict_labels(pipeline: Any, X: List[List[float]]) -> List[int]:
    return pipeline.predict(X)


def predict_probabilities(pipeline: Any, X: List[List[float]]) -> List[List[float]]:
    return pipeline.predict_proba(X)
