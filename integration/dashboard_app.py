"""Local demo entrypoint for the disposable native PostgREST test fixture only."""

from portfolio_forecasting.dashboard import main
from portfolio_forecasting.dashboard_data import Reader, environment_credentials
from portfolio_forecasting.supabase_store import SupabaseStore

main(read=Reader(SupabaseStore(environment_credentials(), api_prefix="")).query)
