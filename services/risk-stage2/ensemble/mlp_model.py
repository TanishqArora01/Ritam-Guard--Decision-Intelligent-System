"""
ensemble/mlp_model.py
PyTorch MLP for Stage 2 fraud detection.
Architecture: 18 → [128→64→32] → 1 with BatchNorm + Dropout
"""
from __future__ import annotations
import logging, time
from typing import Optional
import numpy as np
logger = logging.getLogger(__name__)

try:
    import torch, torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    _TORCH = True
except ImportError:
    _TORCH = False; logger.warning("PyTorch not installed")

try:
    import mlflow, mlflow.pytorch
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
    from sklearn.preprocessing import StandardScaler
    _DEPS = True
except ImportError:
    _DEPS = False

from config import config


class FraudMLP(nn.Module if _TORCH else object):
    def __init__(self, input_dim=18, hidden_dims=None, dropout=0.3):
        super().__init__()
        dims = hidden_dims or config.mlp_hidden_dims
        layers = []
        prev = input_dim
        for i, h in enumerate(dims):
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h), nn.ReLU()]
            if i < len(dims)-1: layers.append(nn.Dropout(dropout))
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)
    def forward(self, x):
        return torch.sigmoid(self.net(x)).squeeze(-1)
    def reconstruction_error(self, x):
        return ((self(x) - x[:,0]) ** 2)


class MLPArtifact:
    def __init__(self, model, scaler, val_metrics: dict, version: str = "local"):
        self.model = model; self.scaler = scaler
        self.val_metrics = val_metrics; self.version = version

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not _TORCH: return np.full(len(X), 0.5)
        X_s = self.scaler.transform(X)
        t = torch.tensor(X_s, dtype=torch.float32)
        self.model.eval()
        with torch.no_grad(): return self.model(t).numpy()


class MLPTrainer:
    def __init__(self):
        if not _TORCH: raise RuntimeError("PyTorch not installed")

    def train(self, X: np.ndarray, y: np.ndarray) -> MLPArtifact:
        X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2,
                                                      random_state=config.random_seed, stratify=y)
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_tr); X_val = scaler.transform(X_val)
        tr_ds = TensorDataset(torch.tensor(X_tr, dtype=torch.float32),
                              torch.tensor(y_tr, dtype=torch.float32))
        val_ds = TensorDataset(torch.tensor(X_val, dtype=torch.float32),
                               torch.tensor(y_val, dtype=torch.float32))
        tr_dl = DataLoader(tr_ds, batch_size=config.mlp_batch_size, shuffle=True)
        val_dl = DataLoader(val_ds, batch_size=512)
        model = FraudMLP(X.shape[1], config.mlp_hidden_dims, config.mlp_dropout)
        crit = nn.BCELoss()
        opt  = torch.optim.Adam(model.parameters(), lr=config.mlp_lr)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=config.mlp_epochs)
        logger.info("Training MLP %d epochs...", config.mlp_epochs)
        t0 = time.perf_counter()
        for epoch in range(config.mlp_epochs):
            model.train()
            for Xb, yb in tr_dl:
                opt.zero_grad()
                loss = crit(model(Xb), yb)
                loss.backward(); opt.step()
            sched.step()
            if (epoch+1) % 10 == 0:
                model.eval()
                preds = []
                with torch.no_grad():
                    for Xb,_ in val_dl: preds.append(model(Xb).numpy())
                auc = roc_auc_score(y_val, np.concatenate(preds))
                logger.info("  epoch %d/%d auc=%.4f", epoch+1, config.mlp_epochs, auc)
        logger.info("MLP trained in %.1fs", time.perf_counter()-t0)
        model.eval()
        preds = []
        with torch.no_grad():
            for Xb,_ in val_dl: preds.append(model(Xb).numpy())
        y_prob = np.concatenate(preds); y_pred = (y_prob>=0.5).astype(int)
        metrics = {
            "val_auc":       float(roc_auc_score(y_val, y_prob)),
            "val_precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "val_recall":    float(recall_score(y_val, y_pred, zero_division=0)),
            "val_f1":        float(f1_score(y_val, y_pred, zero_division=0)),
        }
        logger.info("MLP val: AUC=%.4f P=%.3f R=%.3f", metrics["val_auc"], metrics["val_precision"], metrics["val_recall"])
        version = self._register(model)
        return MLPArtifact(model, scaler, metrics, version)

    def _register(self, model) -> str:
        if not hasattr(mlflow, 'set_tracking_uri'): return "local-no-mlflow"
        try:
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            mlflow.set_experiment(config.mlflow_experiment)
            with mlflow.start_run(run_name=f"stage2-mlp-{int(time.time())}") as r:
                mlflow.pytorch.log_model(model, "mlp_model", registered_model_name=config.mlflow_mlp_name)
                return r.info.run_id[:8]
        except Exception as e:
            logger.warning("MLP MLflow failed: %s", e); return "local-mlflow-failed"


def load_mlp_from_mlflow() -> Optional[MLPArtifact]:
    if not _TORCH: return None
    try:
        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
        client = mlflow.tracking.MlflowClient()
        vs = client.get_latest_versions(config.mlflow_mlp_name, stages=[config.mlflow_model_stage])
        if not vs: return None
        model = mlflow.pytorch.load_model(f"models:/{config.mlflow_mlp_name}/{config.mlflow_model_stage}")
        return MLPArtifact(model, StandardScaler(), {}, f"mlflow-v{vs[0].version}")
    except Exception as e:
        logger.warning("MLP MLflow load failed: %s", e); return None
