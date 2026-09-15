"""Run with: uv run --locked streamlit run streamlit_app.py."""

from portfolio_forecasting.dashboard import main
from portfolio_forecasting.operations import render_status

main()
render_status()
