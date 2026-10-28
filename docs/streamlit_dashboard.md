# Streamlit dashboard

The dashboard is a presentation layer only: it calls the FastAPI service and does not open generated CSV files or recompute forecasting logic.

## Local run

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Generate a dataset if needed: `python -m src.generator --output output/starter`.
4. In one terminal, start the API: `uvicorn api.main:app --reload`.
5. In another terminal, start the dashboard: `streamlit run dashboard/app.py`.

Set `FORECAST_DATASET_DIR` to select a dataset and `FORECAST_API_URL` when the API is not running on `http://127.0.0.1:8000`.

The Executive Overview creates a forecast run. Its identifier is retained in the browser session and is used by all other pages. If the API has no realized outcomes for a live forecast horizon, the dashboard reports actuals, accuracy, calibration, and model comparison as unavailable. It never substitutes synthetic display values.

## Tests

Run `python -m unittest discover -s tests -v`. Dashboard tests cover monetary/missing-value display, pure display filtering, and the outbound forecast API request. FastAPI integration tests run when FastAPI and HTTPX are installed; PostgreSQL integration additionally requires `SALES_FORECAST_TEST_DATABASE_URL`.
