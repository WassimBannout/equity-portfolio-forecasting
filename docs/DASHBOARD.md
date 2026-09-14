# Read-only dashboard

Milestone 5 adds a Streamlit application over the established published-run RPCs.
The browser never downloads market prices, fits Prophet, solves an allocation,
or writes database records. Start it locally from the repository root:

```sh
uv sync --locked
uv run --locked streamlit run streamlit_app.py
```

Inject `SUPABASE_URL` and a reader `SUPABASE_KEY` into the server process first.
A publishable/anonymous project key is sufficient for the M4 published readers.
If an authenticated reader JWT is used, inject `SUPABASE_ACCESS_TOKEN` separately.
The actual database role must be `anon` or `authenticated`; the dashboard rejects
`portfolio_writer` and privileged roles before reading results. No credential
entry field or automatic environment-file loader is provided. See the existing
[database guide](PERSISTENCE_AND_PUBLICATION.md) for schema and credential setup.
Hosted provisioning and public deployment remain Milestone 6.

## Browsing and interpretation

The date selector groups runs by their **forecast target session**, explicitly
labelled in the UI. The initial choice follows the database order: target,
publication timestamp, then run UUID, descending. The second selector identifies
the exact published run and deliberate scientific revision. A run is fetched as
one complete JSON aggregate; its identity, complete asset membership, immutable
scientific payload, weights, date/value histories, and presentation provenance
must validate before its portfolio is drawn.

Run summaries have 25 records per page. **Older runs** and **Newer runs** navigate
stable keyset pages. Multiple revisions for a date can extend across page
boundaries; the page caption states this. No date is offered on the basis of
independently latest ticker rows, and the selected run is never assembled from
multiple pages or attempts.

The overview shows adjusted USD forecasts, fractional returns formatted as
percentages, the allocation doughnut and a numeric allocation column. It states
the stored cutoff, target, execution/completion/publication timestamps in UTC,
Prophet version, scientific configuration revision, and full source revision.
The provenance expander includes effective model settings, configuration, lock
and input hashes, and dated retrieval metadata. Allocation policy explains the
floor, effective concentration ceiling, risk aversion and full-investment rule.

Tickers are alphabetical. The three asset metrics belong to the selected run:
its stored cutoff observation, target prediction and forecast return. The actual
metric is never replaced by a later run or a live quote. A separate outcome notice
shows whether the exact target has a comparable actual. The dated-observation
expander preserves every stored session/value pair, including gaps on exchange
closures; no weekday sequence is invented.

The historical panel browses **all available published predictions for the chosen
ticker**, independently of the selected run. Its inclusive database query bounds
are 0001-01-01 through 9999-12-31. Retrieval, tables and charts remain bounded to
25 predictions per page; older and newer history controls are independent of run
navigation. Captions show the page number, actual target-date coverage, prediction,
matched, pending and incompatible counts, and whether older predictions remain.
Changing the ticker or refreshing the publication watermark starts its first page.

The Plotly comparison uses recorded forecast target dates, with explicit date-only
ticks and padded day bounds even for one session. Pending forecasts remain
visible with a missing actual, and missing actuals remain gaps. Hover exposes the
date, price, run and revision. The price-range slider controls the vertical axis;
Plotly also supports zoom, pan, legend interaction and reset. Lines connect stored
predictions, not unobserved intervening prices. Deliberate revisions are retained
as distinct predictions; each actual retains its own run's comparable price basis.

## Error metrics

The error table retains every prediction on the current history page, including
pending/incompatible entries with **Unavailable** values. Matched outcomes use
the exact stored target and M4's unchanged-overlap adjusted-price basis policy.

- Signed price error: `actual - predicted`, in USD.
- Absolute price error: the magnitude of signed error, in USD.
- Percentage error: `100 * (actual - predicted) / predicted`. The prediction is
  the denominator; this is not MAPE.
- Price MAE and RMSE: matched predictions on the **current page only**.
- Last-price MAE: the same matched predictions, using each run's stored cutoff
  price as its baseline. The relative MAE divides forecast MAE by baseline MAE.
  A zero baseline denominator is explicitly undefined, including when both
  methods are perfect; no missing scientific value becomes zero or a unit ratio.

Each published revision counts separately. Sample counts refer to predictions,
not independent sessions. These page diagnostics do not replace the chronological
[M3 research comparison](examples/milestone3/MODEL_SELECTION.md), aggregate across
unloaded pages, establish forecasting advantage, or represent executable returns.

## State guide

| State | Visible behavior |
| --- | --- |
| No published runs | Informational message explaining that a completed batch must publish results; no empty selectors or charts |
| First run / outcome pending | Allocation, forecast table, selected metrics, dated observations and forecast chart render; evaluation remains pending |
| One ticker without outcomes | That ticker remains usable; other ticker outcomes and the portfolio are unaffected |
| Incompatible outcome basis | Explicit unavailable notice; actual/errors remain unavailable while the issued forecast is preserved |
| Bad selected run | Explicit **Bad record** message; no portfolio chart, normalized partial pie, or fabricated numeric values |
| Bad history page | Explicit **Bad record** message in the history section; validated selected-run views remain available |
| Missing/rejected credentials or storage outage | Explicit **Service unavailable** message with connection/retry guidance; distinct from an empty database; no raw exception or credential output |
| Constant or single-point series | Padded finite price bounds permit valid plotting |
| Equal slider endpoints | Guidance to choose distinct endpoints; chart withheld while the table remains visible |
| Nonfinite/overflowing chart data | Explicit invalid-chart message; no invalid axis construction |
| Older live run | Latest already-opened XNYS session is compared with the stored target and an older-result notice is displayed |
| Retrospective run | Explicit research label; never presented as a current live forecast |

## Cache and coherence boundaries

`st.cache_data` caches read results for 300 seconds, with at most 128 entries and
no persistent disk cache. Credentials, query name and arguments all participate in
the cache key, preventing different reader connections from sharing an entry.
Expiry causes a new read on the **next access**; it does not schedule a background
refresh. Clock-based freshness is evaluated on each UI run. A new first-page
publication watermark resets pagination; each later page uses the same watermark.

The run aggregate is coherent at one database read. The publication watermark
does not freeze subsequent outcome vintages or create a long-lived MVCC snapshot
across pages. Run and history caches can have different fetch times within the
declared interval. Outcome notices/tables use their own returned evidence; no
cross-query scientific values are joined. On an uncached failure there is no
hidden last-good fallback labelled as current data.

## Verification and recorded demonstration

```sh
make check
make database-smoke
make package-smoke
```

The standard offline suite includes Streamlit AppTest interactions and pure
contract checks. The database gate includes a synthetic twelve-asset request,
twelve real Prophet fits, allocation/publication, a complete anonymous read under
PostgREST's three-row test cap, the first pending dashboard render, later exact
outcome ingestion, and the rendered comparison. Existing M4 permissions and
database tests remain part of the same gate.

The explicit browser demonstration uses an isolated optional test driver and the
existing local Chrome binary; it adds no application dependency or deployed API:

```sh
uv venv /tmp/portfolio-m5-browser
uv pip install --python /tmp/portfolio-m5-browser/bin/python playwright==1.58.0
M5_RECORD_DEMO=1 \
M5_BROWSER_PYTHON=/tmp/portfolio-m5-browser/bin/python \
uv run --locked python -m pytest integration/test_dashboard.py -v
```

This starts temporary native database/PostgREST and loopback Streamlit processes,
checks actual tooltip, range-slider and Plotly zoom behavior in Chrome, and stops
the processes. It requires `/usr/bin/google-chrome` and the existing M4 database
prerequisites. The test-only Streamlit entrypoint uses the native PostgREST path;
the product entrypoint uses Supabase's `/rest/v1` path.

Outputs are in ignored `artifacts/milestone5/demo/`. Selected portable screenshots
and rendered evidence are retained in [the demonstration](examples/milestone5/README.md).
Exact results and limitations are recorded in [MILESTONE_5_REPORT.md](../MILESTONE_5_REPORT.md).
