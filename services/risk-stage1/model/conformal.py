"""
model/conformal.py
Inductive Conformal Prediction (ICP) for uncertainty quantification.

Theory:
  ICP provides a formal statistical guarantee:
      P(true label IN prediction set) ≥ 1 - α

  where α is the significance level (default 0.05 → 95% coverage).

  This is a stronger guarantee than Platt scaling or isotonic regression
  because it holds WITHOUT assumptions on the data distribution.

Algorithm (binary classification):
  Calibration phase (one-time, run after training):
    1. Score calibration examples with the model: ŝ = model.predict(X_cal)
    2. For each calibration example i with true label y_i:
         nonconformity_score_i = 1 - ŝ_i   if y_i == 1 (fraud)
                               = ŝ_i        if y_i == 0 (legit)
    3. Compute the (1-α) quantile of these scores → q_hat

  Inference phase (per transaction):
    1. Score the test example: p = model.predict(x)
    2. p-value for fraud class:
         pv_fraud = |{i: score_i ≤ 1 - p}| / (n_cal + 1)
    3. p-value for legit class:
         pv_legit = |{i: score_i ≤ p}| / (n_cal + 1)
    4. Prediction set at level α:
         include class c if pv_c > α
    5. Uncertainty = 1 - max(pv_fraud, pv_legit)
         → 0.0 = perfectly certain, 1.0 = completely uncertain

Reference:
  Vovk, Gammerman, Shafer (2005). "Algorithmic Learning in a Random World."
"""
from __future__ import annotations

import logging
import pickle
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ConformalPredictor:
    """
    Inductive Conformal Predictor for binary fraud classification.

    Calibrate once after training, then call predict() at inference time.
    Calibration scores are stored as a sorted numpy array for O(log N)
    quantile lookup via np.searchsorted.
    """

    def __init__(self, alpha: float = 0.05):
        """
        Args:
            alpha: significance level. 0.05 → 95% coverage guarantee.
        """
        self.alpha            = alpha
        self._cal_scores: Optional[np.ndarray] = None   # sorted nonconformity scores
        self._n_cal:      int = 0
        self._q_hat:      float = 1.0                   # (1-α) quantile of cal scores

    @property
    def is_calibrated(self) -> bool:
        return self._cal_scores is not None

    # -------------------------------------------------------------------------
    # Calibration
    # -------------------------------------------------------------------------

    def calibrate(
        self,
        y_prob: np.ndarray,   # model P(fraud) on calibration set
        y_true: np.ndarray,   # true binary labels (1=fraud, 0=legit)
    ):
        """
        Compute and store calibration nonconformity scores.
        Call this once after training on a held-out calibration set.
        """
        assert len(y_prob) == len(y_true), "y_prob and y_true must have same length"
        assert len(y_prob) > 0, "Calibration set must not be empty"

        # Nonconformity score: how "surprising" is this example given the model?
        # Fraud examples:   score = 1 - p_fraud  (low score = model is confident it's fraud)
        # Legit examples:   score = p_fraud       (low score = model is confident it's legit)
        scores = np.where(
            y_true == 1,
            1.0 - y_prob,    # fraud nonconformity
            y_prob,          # legit nonconformity
        )

        self._cal_scores = np.sort(scores)
        self._n_cal      = len(scores)

        # Compute the corrected (1-α) quantile
        # The +1 in the numerator and denominator is the finite-sample correction
        # that ensures the coverage guarantee holds exactly.
        quantile_level   = np.ceil((self._n_cal + 1) * (1 - self.alpha)) / self._n_cal
        quantile_level   = min(quantile_level, 1.0)
        self._q_hat      = float(np.quantile(self._cal_scores, quantile_level))

        logger.info(
            "ICP calibrated: n_cal=%d | α=%.2f | q_hat=%.4f",
            self._n_cal, self.alpha, self._q_hat,
        )

    # -------------------------------------------------------------------------
    # Inference
    # -------------------------------------------------------------------------

    def predict(self, p_fraud: float) -> Tuple[bool, float, float, float]:
        """
        Compute conformal uncertainty for a single prediction.

        Args:
            p_fraud: model output P(fraud) ∈ [0, 1]

        Returns:
            (conformal_includes_fraud, uncertainty, pv_fraud, pv_legit)

            conformal_includes_fraud:
                True  → fraud class is in the (1-α) prediction set
                False → model is confident this is NOT fraud
            uncertainty:
                0.0  = perfectly certain (model is very confident)
                1.0  = completely uncertain (model has no idea)
            pv_fraud:  p-value for the fraud class
            pv_legit:  p-value for the legit class
        """
        if not self.is_calibrated:
            logger.warning("ConformalPredictor not calibrated — returning defaults")
            return True, 1.0, 0.5, 0.5

        n  = self._n_cal
        scores = self._cal_scores

        # p-value for FRAUD class:
        # Nonconformity of x under fraud hypothesis = 1 - p_fraud
        nc_fraud = 1.0 - p_fraud
        # Count calibration scores ≥ nc_fraud  (how many cal examples are at
        # least as "non-conforming" as this test example under the fraud class)
        pv_fraud = float(np.searchsorted(scores, nc_fraud, side="right")) / (n + 1)
        # Correction: include +1 in denominator for finite sample guarantee
        pv_fraud = (np.sum(scores >= nc_fraud) + 1) / (n + 1)

        # p-value for LEGIT class:
        nc_legit = p_fraud
        pv_legit = (np.sum(scores >= nc_legit) + 1) / (n + 1)

        # Prediction set: include class if p-value > α
        conformal_includes_fraud = pv_fraud > self.alpha

        # Uncertainty: 1 - confidence
        # Confidence = how much better the best class's p-value is vs α
        uncertainty = float(1.0 - max(pv_fraud, pv_legit))
        uncertainty = max(0.0, min(1.0, uncertainty))

        return conformal_includes_fraud, uncertainty, pv_fraud, pv_legit

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save(self, path: str):
        with open(path, "wb") as f:
            pickle.dump({
                "alpha":      self.alpha,
                "cal_scores": self._cal_scores,
                "n_cal":      self._n_cal,
                "q_hat":      self._q_hat,
            }, f)

    def load(self, path: str):
        with open(path, "rb") as f:
            d = pickle.load(f)
        self.alpha        = d["alpha"]
        self._cal_scores  = d["cal_scores"]
        self._n_cal       = d["n_cal"]
        self._q_hat       = d["q_hat"]
        logger.info("ICP loaded: n_cal=%d q_hat=%.4f", self._n_cal, self._q_hat)
