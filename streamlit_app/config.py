"""Streamlit Application Configuration & Theme Constants."""
import os
import sys
from pathlib import Path

# Add project root to sys.path so ml package can be imported if needed
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Backend service connection configuration
BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_TIMEOUT_SECONDS = float(os.environ.get("API_TIMEOUT_SECONDS", "5.0"))

# Application metadata
APP_TITLE = "ApexGuard | Banking Transaction & Fraud Detection"
APP_SUBTITLE = "Real-Time Transaction Monitoring & Explainable Fraud AI"
APP_ICON = "🛡️"

# Risk threshold & bands (aligned with ml.config)
CLASSIFICATION_THRESHOLD = 0.2100
RISK_LOW_LIMIT = 0.10
RISK_MEDIUM_LIMIT = 0.21

# Visual badge styling & colors
COLOR_LEGITIMATE = "#28a745"
COLOR_FRAUDULENT = "#dc3545"
COLOR_RISK_LOW = "#28a745"
COLOR_RISK_MEDIUM = "#fd7e14"
COLOR_RISK_HIGH = "#dc3545"

# Global explanation artifact directory
REPORTS_FIGURES_DIR = ROOT_DIR / "ml" / "reports" / "figures"
GLOBAL_BAR_PLOT_PATH = REPORTS_FIGURES_DIR / "shap_feature_importance_bar.png"
GLOBAL_BEESWARM_PLOT_PATH = REPORTS_FIGURES_DIR / "shap_summary_beeswarm.png"
