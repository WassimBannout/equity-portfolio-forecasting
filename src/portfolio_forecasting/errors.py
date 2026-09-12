"""Stage-aware failures for the finite market-data-to-forecast computation."""


class ForecastError(ValueError):
    def __init__(self, stage: str, message: str, *, ticker: str | None = None):
        self.stage = stage
        self.ticker = ticker
        super().__init__(f"{stage}{' [' + ticker + ']' if ticker else ''}: {message}")
