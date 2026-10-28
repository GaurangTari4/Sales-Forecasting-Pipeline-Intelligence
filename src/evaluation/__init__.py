"""Leak-safe forecasting backtests and report generation."""
from .backtest import evaluate_forecasts, evaluate_anomalies
from .historical import completed_snapshots, run_historical_backtest
from .reporting import write_evaluation_report
__all__ = ["evaluate_forecasts", "evaluate_anomalies", "write_evaluation_report", "completed_snapshots", "run_historical_backtest"]
