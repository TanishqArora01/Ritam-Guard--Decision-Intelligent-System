"""
anomaly/detectors.py
Anomaly detection using Autoencoder + Isolation Forest, combined.

Autoencoder (PyTorch):
  Trained ONLY on legitimate transactions — learns the "normal" manifold.
  At inference, the reconstruction error for a fraud transaction is high
  because the autoencoder cannot reconstruct patterns it never saw.

  Architecture: Encoder 18→12→6, Decoder 6→12→18
  Loss: MSE reconstruction error
  Anomaly score = normalised MSE against calibration percentile

Isolation Forest (sklearn):
  Unsupervised tree-based anomaly detector.
  Isolates anomalies with fewer splits than normal points.
  Contamination parameter matches the expected fraud rate.
  Fast inference (no gradient computation needed).

Combined score:
  anomaly = ae_weight * ae_score + if_weight * if_score
  Default: 0.6 * AE + 0.4 * IF
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

try:
    import mlflow
    _MLFLOW_AVAILABLE = True
except ImportError:
    _MLFLOW_AVAILABLE = False

from config import config


# ---------------------------------------------------------------------------
# Autoencoder Network
# ---------------------------------------------------------------------------

class FraudAutoencoder(nn.Module if _TORCH_AVAILABLE else object):
    """
    Symmetric encoder-decoder.
    Encoder: [18 → 12 → 6]  (compression)
    Decoder: [6 → 12 → 18]  (reconstruction)
    """

    def __init__(self, input_dim: int = 18, encoding_dims: list = None):
        super().__init__()
        dims = encoding_dims or config.ae_encoding_dims

        # Encoder: first half up to bottleneck
        mid = len(dims) // 2
        enc_layers = []
        for i in range(mid):
            enc_layers += [nn.Linear(dims[i], dims[i+1]), nn.ReLU()]
        self.encoder = nn.Sequential(*enc_layers)

        # Decoder: from bottleneck back to input size
        dec_layers = []
        for i in range(mid, len(dims)-1):
            dec_layers += [nn.Linear(dims[i], dims[i+1]), nn.ReLU()]
        dec_layers.append(nn.Sigmoid())  # output in [0,1] after scaling
        self.decoder = nn.Sequential(*dec_layers)

    def forward(self, x):
        return self.decoder(self.encoder(x))

    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        """Per-sample MSE reconstruction error."""
        recon = self(x)
        diff  = recon - x
        return (diff ** 2).mean(dim=-1)


# ---------------------------------------------------------------------------
# Autoencoder Artifact
# ---------------------------------------------------------------------------

class AutoencoderArtifact:

    def __init__(self, model, scaler, threshold_95: float, version: str = "local"):
        self.model        = model          # FraudAutoencoder
        self.scaler       = scaler         # StandardScaler (fit on legit data)
        self.threshold_95 = threshold_95   # 95th percentile reconstruction error on legit
        self.version      = version

    def anomaly_score(self, X: np.ndarray) -> np.ndarray:
        """
        Return normalised anomaly score in [0,1] for each sample.
        0.0 = normal, 1.0 = highly anomalous.
        """
        if not _TORCH_AVAILABLE:
            return np.full(len(X), 0.0)

        X_scaled = self.scaler.transform(X)
        tensor   = torch.tensor(X_scaled, dtype=torch.float32)
        self.model.eval()
        with torch.no_grad():
            errors = self.model.reconstruction_error(tensor).numpy()

        # Normalise: score = error / threshold_95, capped at 1.0
        scores = np.clip(errors / max(self.threshold_95, 1e-8), 0.0, 2.0) / 2.0
        return scores


# ---------------------------------------------------------------------------
# Isolation Forest Artifact
# ---------------------------------------------------------------------------

class IsolationForestArtifact:

    def __init__(self, clf, scaler, version: str = "local"):
        self.clf     = clf      # sklearn IsolationForest
        self.scaler  = scaler
        self.version = version

    def anomaly_score(self, X: np.ndarray) -> np.ndarray:
        """
        Return normalised anomaly score in [0,1].
        IsolationForest.score_samples() returns negative values:
          more negative → more anomalous.
        We flip and normalise to [0,1].
        """
        if not _SKLEARN_AVAILABLE:
            return np.full(len(X), 0.0)

        X_scaled = self.scaler.transform(X)
        raw      = self.clf.score_samples(X_scaled)  # range roughly [-1, 0]
        # Flip and normalise: most anomalous → score near 1.0
        scores   = np.clip((-raw - 0.0) / 1.0, 0.0, 1.0)
        return scores


# ---------------------------------------------------------------------------
# Combined Anomaly Detector
# ---------------------------------------------------------------------------

class AnomalyDetector:

    def __init__(self, ae: AutoencoderArtifact, iforest: IsolationForestArtifact):
        self.ae      = ae
        self.iforest = iforest
        self.ae_w    = config.anomaly_ae_weight
        self.if_w    = config.anomaly_if_weight

    def score(self, X: np.ndarray) -> Tuple[float, float, float]:
        """
        Score a single transaction.
        Returns (combined_score, ae_score, if_score) all in [0,1].
        """
        ae_scores = self.ae.anomaly_score(X)
        if_scores = self.iforest.anomaly_score(X)

        ae_s = float(ae_scores[0]) if len(ae_scores) > 0 else 0.0
        if_s = float(if_scores[0]) if len(if_scores) > 0 else 0.0

        combined = self.ae_w * ae_s + self.if_w * if_s
        return round(combined, 4), round(ae_s, 4), round(if_s, 4)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class AnomalyTrainer:

    def train(
        self, X_legit: np.ndarray
    ) -> Tuple[AutoencoderArtifact, IsolationForestArtifact]:
        """
        Train both detectors on legitimate-only data.
        Returns (AutoencoderArtifact, IsolationForestArtifact).
        """
        ae_artifact = self._train_autoencoder(X_legit)
        if_artifact = self._train_isolation_forest(X_legit)
        return ae_artifact, if_artifact

    def _train_autoencoder(self, X: np.ndarray) -> AutoencoderArtifact:
        if not _TORCH_AVAILABLE:
            logger.warning("PyTorch unavailable — using dummy autoencoder")
            from sklearn.preprocessing import StandardScaler
            return AutoencoderArtifact(None, StandardScaler().fit(X), 1.0, "dummy")

        from sklearn.preprocessing import MinMaxScaler
        scaler   = MinMaxScaler()
        X_scaled = scaler.fit_transform(X)

        dataset = TensorDataset(torch.tensor(X_scaled, dtype=torch.float32))
        loader  = DataLoader(dataset, batch_size=config.ae_batch_size, shuffle=True)

        model     = FraudAutoencoder(X.shape[1], config.ae_encoding_dims)
        optimizer = torch.optim.Adam(model.parameters(), lr=config.ae_lr)
        criterion = nn.MSELoss()

        logger.info("Training Autoencoder (%d samples, %d epochs)...",
                    len(X), config.ae_epochs)
        t0 = time.perf_counter()
        for epoch in range(config.ae_epochs):
            model.train()
            total_loss = 0.0
            n_batches  = 0
            for (Xb,) in loader:
                optimizer.zero_grad()
                recon = model(Xb)
                loss  = criterion(recon, Xb)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
                n_batches  += 1

            if (epoch + 1) % 10 == 0:
                avg = total_loss / max(n_batches, 1)
                logger.info("  AE epoch %d/%d  avg_loss=%.6f",
                            epoch+1, config.ae_epochs, avg)

        logger.info("Autoencoder trained in %.1fs", time.perf_counter() - t0)

        # Compute 95th percentile reconstruction error on legit data
        model.eval()
        X_t   = torch.tensor(X_scaled, dtype=torch.float32)
        with torch.no_grad():
            errors = model.reconstruction_error(X_t).numpy()
        threshold_95 = float(np.percentile(errors, 95))
        logger.info("AE threshold_95 = %.6f", threshold_95)

        self._register_ae_mlflow(model)
        return AutoencoderArtifact(model, scaler, threshold_95)

    def _train_isolation_forest(self, X: np.ndarray) -> IsolationForestArtifact:
        if not _SKLEARN_AVAILABLE:
            return IsolationForestArtifact(None, None, "dummy")

        from sklearn.preprocessing import StandardScaler
        scaler   = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        logger.info("Training Isolation Forest (%d samples)...", len(X))
        t0  = time.perf_counter()
        clf = IsolationForest(
            n_estimators  = config.if_n_estimators,
            contamination = config.if_contamination,
            n_jobs        = config.if_n_jobs,
            random_state  = config.random_seed,
        )
        clf.fit(X_scaled)
        logger.info("Isolation Forest trained in %.1fs", time.perf_counter() - t0)

        self._register_if_mlflow(clf)
        return IsolationForestArtifact(clf, scaler)

    def _register_ae_mlflow(self, model):
        if not _MLFLOW_AVAILABLE or not _TORCH_AVAILABLE:
            return
        try:
            import mlflow.pytorch
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            mlflow.set_experiment(config.mlflow_experiment)
            with mlflow.start_run(run_name=f"stage2-ae-{int(time.time())}"):
                mlflow.pytorch.log_model(
                    model, "ae_model",
                    registered_model_name=config.mlflow_ae_name,
                )
        except Exception as e:
            logger.warning("AE MLflow registration failed: %s", e)

    def _register_if_mlflow(self, clf):
        if not _MLFLOW_AVAILABLE:
            return
        try:
            import mlflow.sklearn
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            mlflow.set_experiment(config.mlflow_experiment)
            with mlflow.start_run(run_name=f"stage2-if-{int(time.time())}"):
                mlflow.sklearn.log_model(
                    clf, "if_model",
                    registered_model_name=f"{config.mlflow_ae_name}_iforest",
                )
        except Exception as e:
            logger.warning("IF MLflow registration failed: %s", e)
