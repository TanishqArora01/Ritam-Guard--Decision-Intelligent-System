"""dataset-pipeline/main.py — Dataset export entrypoint."""
from __future__ import annotations

import logging
import os
import sys

from config import config
from synthetic_exporter import export_synthetic
from real_exporter import export_real
from packager import package

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("dataset-pipeline")


def run():
    logger.info("=" * 55)
    logger.info("Fraud Detection — Dataset Export Pipeline")
    logger.info("Version: %s", config.dataset_version)
    logger.info("=" * 55)

    output_dir = config.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # 1. Synthetic dataset
    logger.info("Step 1/3: Generating synthetic dataset…")
    syn_paths, syn_rows = export_synthetic(output_dir)
    logger.info("Synthetic: %d rows exported", len(syn_rows))

    # 2. Real dataset
    logger.info("Step 2/3: Exporting real decisions…")
    real_paths, real_rows = export_real(output_dir)
    if real_rows:
        logger.info("Real: %d rows exported", len(real_rows))
    else:
        logger.info("Real: no data available (PostgreSQL may be empty)")
        real_paths, real_rows = None, None

    # 3. Package
    logger.info("Step 3/3: Packaging…")
    minio_path = package(output_dir, syn_paths, syn_rows, real_paths, real_rows)

    logger.info("=" * 55)
    logger.info("Dataset export complete")
    if minio_path:
        logger.info("Available at: %s", minio_path)
    logger.info("=" * 55)


if __name__ == "__main__":
    run()
