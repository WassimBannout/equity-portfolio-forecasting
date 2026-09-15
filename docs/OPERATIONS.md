# Deployment and daily operation

Milestone 6 supplies a VPS release path and operational checks for the existing
application. **No production host, domain, Supabase project, deployment key or
market-data display authorisation is configured. No live URL or prospective run
is claimed.** Local verification is recorded in [M6 report](../MILESTONE_6_REPORT.md).
This is the final planned milestone; outstanding items are commissioning checks.

## Release and execution contract

The [Release workflow](../.github/workflows/release.yml) is manually dispatched on
`main`. It calls the existing full Quality workflow at the **same commit** and
releases only if every gate succeeds. Checkout explicitly uses `github.sha`;
`git archive` transfers that commit, including its global PAX commit identifier.
The root-owned SSH gateway rejects a mismatched revision, oversized archive,
unsafe paths, links and privileged modes. The deployment key is trusted to supply
reviewed release code: archive metadata is an identity check, not a cryptographic
signature or independent proof of CI approval. Protect the production environment
and main branch to enforce that trust boundary.

Each release has a new directory under `/srv/portfolio/releases/`, a fresh
`uv sync --locked --no-dev --no-editable --python 3.12.14` environment, and
`release.json` containing Git revision, lock hash and package source hash.
Nothing pulls a mutable branch on the host. Python is installed once under
`/opt/pf-python`, then made root-owned; deployments prohibit Python downloads.
The pinned uv executable is root-owned. Runtime packages retain all 78 locked
identities and artifact hashes from Milestone 5; no dependency was added.
OS packages remain the administrator's security-maintained Ubuntu packages.

An atomic `current` symlink selects a release. The non-root dashboard service's
`ExecStartPost` checks Streamlit health, installed source/lock identity, the actual
reader role, and a complete validated published result if one exists. An empty
new database reports `latest_run: null`; initial service readiness does not prove
that a live forecast exists. Only successful readiness updates `last-good`.
A failure restores and rechecks it, and still reports failure. Restart clears
   the dashboard start-limit state so a failed candidate cannot prevent recovery. `previous` retains
the former good release. If switching was interrupted, `rollback` selects
`last-good`; otherwise it selects `previous`. Failure of recovery itself is a
visible failure requiring the operator. No release deletes prior directories or
changes database schema. First deployment has no older release to restore.

The workflow also verifies public HTTPS health with normal certificate/hostname
validation and bounded retries; failure attempts rollback. A first-release TLS
failure cannot restore a nonexistent predecessor. SSH status and readiness output
identify the exact serving release; Streamlit's generic health URL alone does not.

## Clean-host setup (operator, not executed here)

Use a new authorised **Ubuntu 24.04 Linux x86-64 VPS**, with enough memory for the
locked native libraries, twelve sequential fits, and Streamlit. Start with 4 GiB
RAM and measure the first full run; systemd's batch timeout bounds computation.
Keep an administrative console/session open throughout SSH/firewall changes.
Use a reviewed checkout of the exact revision that passes Quality.

1. Provision the Supabase schema and restricted roles using the existing
   [migration/permission guide](PERSISTENCE_AND_PUBLICATION.md). Supply separate
   reader credentials and a trusted short-lived `portfolio_writer` JWT. Verify
   them through the actual hosted gateway. Neither workload receives a signing
   key, service-role key, administrator password or database migration rights.
2. Record the intended data retention/public display use and its authorisation.
   Set the production environment variable `PF_DATA_USE_APPROVED=true` only once
   this external requirement is resolved. The release workflow fails closed
   while it is absent. No data-rights conclusion is inferred from API access.
3. Create a new Ed25519 deployment key and retain its private half only in the
   GitHub production environment secret store. Copy its **public** half to the
   administrative host session. Obtain the SSH host public key/fingerprint from
   the provider console or another independently trusted channel. Do not create
   `known_hosts` by trusting a network scan during deployment.
4. Obtain the official **uv 0.12.13 Linux x86-64** binary. The provisioning script
   requires SHA-256
   `b59310db262709ee92baf7954ef30820f1442ffa48b263f7001a236fe9004047`, the binary used
   for local checks. For example download the pinned release from the
   [official uv release](https://github.com/astral-sh/uv/releases/tag/0.12.13),
   extract it as an ordinary user and compare the binary hash before use. A
   different build must be separately reviewed/tested, not silently substituted.
5. Run the clean-host bootstrap with your real domain, verified uv binary and
   public deployment key. This explicitly installs host packages and identities:

   ```sh
   sudo bash deploy/provision.sh forecasts.YOUR_DOMAIN /path/to/uv /path/to/deploy.pub
   ```

   The script creates `pf-deploy` (release access), `pf-web` (reader), and
   `pf-batch` (restricted writer). `pf-deploy` has only four exact sudo commands:
   restart/reset the dashboard failure state, start the batch, and start the
   freshness check. Its
   root-owned authorised key forces the bounded gateway command and disables
   passwords, TTYs, forwarding and user startup scripts. The gateway rejects root
   execution. Keep the root-owned home/SSH restrictions intact. This script is
   for a dedicated clean host; it refuses an existing active release. Routine
   releases do not re-run provisioning or modify systemd/sudo/SSH configuration.
6. Inject `/etc/portfolio/reader.env` and `/etc/portfolio/writer.env` using the
   operator's secure administrative channel; owner `root:root`, mode `0600`,
   parent mode `0700`. These are systemd EnvironmentFile entries, not shell
   scripts. Never commit them, echo them in logs, or put secrets in command-line
   arguments. Reader file: `SUPABASE_URL`, `SUPABASE_KEY`. Writer file: these names
   plus `SUPABASE_ACCESS_TOKEN`. Readers must omit the writer token. Rotate the
   writer JWT before expiry through the existing trusted issuer; a publishable
   API key cannot mint it. The project deliberately adds no token issuer.
7. Point the domain's A record at the VPS. Publish AAAA only if IPv6 reaches it.
   Permit inbound TCP 80/443; restrict SSH to the operator/Actions access policy.
   Never expose port 8501 (the service binds loopback) or PostgreSQL. Permit
   outbound DNS, HTTPS for packages/provider/Supabase/ACME, and time synchronisation.
   Verify the host UTC clock with `timedatectl status`. Firewall/provider security
   rules are operator-specific and must be verified from outside the VPS.
8. Validate and start the proxy after DNS/ports are correct:

   ```sh
   sudo systemd-analyze verify /etc/systemd/system/pf-*.service /etc/systemd/system/pf-freshness.timer
   sudo visudo -cf /etc/sudoers.d/portfolio
   sudo sshd -t
   sudo systemctl restart caddy.service
   ```

   The Caddy unit reads `PF_DOMAIN` from its root-owned override. Caddy manages
   public ACME certificates and HTTP-to-HTTPS redirects. Its standard service
   runs as `caddy`. The deployment user cannot configure the proxy or issue root
   shell commands. Before an application release the proxy may return 502.

## GitHub configuration and first release

Configure a `production` Actions environment restricted to the protected `main`
branch. Choose environment approval policy so the daily scheduled job can execute
unattended under the authorised policy. Require the Quality check for changes to
main; restrict workflow/secret editing to operators. Enable Actions and failed-run
notifications for the responsible operator. No `pull_request_target` workflow or
workflow-run artifact from an untrusted PR receives deployment secrets.

| Name | Storage | Value |
| --- | --- | --- |
| `SSH_HOST` | production variable | VPS DNS name or IPv4 address, SSH port 22 |
| `SSH_PRIVATE_KEY` | production secret | New dedicated deployment private key |
| `SSH_KNOWN_HOSTS` | production secret | Exact trusted OpenSSH known_hosts entry for SSH_HOST |
| `PF_PUBLIC_URL` | production variable | `https://forecasts.YOUR_DOMAIN`, no trailing slash |
| `PF_DATA_USE_APPROVED` | production variable | `true` only with recorded intended-use authorisation |

SSH always uses `pf-deploy`, strict host checking, only the supplied key, no agent
forwarding, one connection attempt, a 10-second connection timeout and bounded
keepalives. The script uses mode-0700 temporary storage and deletes key files on
exit. No third-party SSH action is used; checkout/setup-uv retain immutable SHA
pins. Workflows have only `contents: read`. HTTPS uses normal CA verification.

Dispatch **Release** on main. Review the exact revision and readiness output,
then independently check HTTPS and the live read-only dashboard. On the host:

```sh
sudo systemctl status pf-dashboard.service caddy.service
sudo systemctl start pf-freshness.timer
sudo systemctl list-timers pf-freshness.timer
sudo journalctl -u pf-dashboard.service --since today
```

Verify actual process identities, denied writer/admin reader access, private file
permissions, SSH host-key rejection, and no externally reachable port 8501. Inspect
certificate issuer/hostname and HTTP redirect. These host checks are still pending.
Update root-owned helper/unit files only through an explicit administrative change
reviewed with the release; a code release does not silently replace privileged
configuration. Preserve compatible helpers with retained releases for recovery.

## Daily schedule, deadlines and freshness

[Daily publication](../.github/workflows/daily.yml) requests the active release at
**09:00 UTC daily**, plus manual dispatch. Forecasting runs on the VPS as
`pf-batch`; Actions does not independently install/run a mutable branch's model.
Every batch logs its Git revision and the established run/attempt/stage diagnostics.
The unit is oneshot, without automatic restarts. Repeated successful identities
return `no_op / already_published`; closed sessions return `no_op / closed_session`.
Repeated jobs still attempt bounded outcome recovery. No weekend/holiday fit is
performed, and late live requests fail before data access. M2/M4 enforce data
freshness and recheck the pre-open deadline through the final database transaction.

Release and daily workflows share a concurrency group with cancellation disabled.
GitHub can replace an older pending workflow when several are queued; this is not
an unlimited work queue. A host `flock` additionally excludes release and batch
execution across manual/SSH paths. A busy lock fails visibly instead of waiting
until a live target has expired. systemd coalesces simultaneous starts of the same
oneshot unit; there is only one batch process. Database uniqueness/atomicity remain
the final cross-client publication protection. Administrative bypass of these
entrypoints is outside that overlap guarantee.

| Bound | Policy |
| --- | --- |
| Provider | Existing three attempts per asset, 30-second socket timeout, bounded backoff |
| Supabase | Existing three attempts, 15-second socket timeout, 1/2-second backoff, transient errors only |
| Whole batch | 1,400-second timeout, 10-second kill grace; systemd startup bound 1,450 seconds |
| Release install | 900 seconds; failed install cannot change current |
| Local readiness | Three probes, at most 50 seconds each; systemd startup bound 180 seconds |
| SSH / Actions | Remote command 1,700 seconds; SSH 1,650 seconds; daily job 30 minutes |
| Freshness monitor | 150 seconds plus kill grace, every 15 minutes on the VPS |
| Freshness history | At most ten pages of 100 summaries, complete-read validation for candidate live results |
| Outcome catch-up | At most five pages of 50 runs within the preceding 14 calendar days |

The one-hour scheduling allowance ends at **10:00 UTC** on eligible XNYS dates.
Before then the previous session is due; after then today's session is due.
Weekends, holidays, year boundaries and US daylight-saving changes use the existing
exchange calendar. Freshness checks require the default universe, scientific
revision and effective settings in a complete **live** run; a newer retrospective
result cannot clear the alert. Source revisions may differ across legitimate
releases. History scan exhaustion reports unknown, not fresh.

The VPS timer only reads results; it never starts forecasts. This independent check
can detect an absent GitHub run. It writes atomic sanitized status to
`/var/lib/pf-status/status.json`, and failure has a nonzero unit exit and journal
entry. The dashboard footer shows expected target, last successful live publication,
cutoff, run ID and check time. An unavailable database preserves a clearly labelled
last-known success. A status file older than 30 minutes is explicitly overdue;
missing/malformed status is unknown. This footer refreshes when a visitor reruns
the page, consistent with the existing Streamlit UI. It is not an out-of-band pager.
Actions displays status in its job summary and fails on publication/freshness error.
The host cannot independently alert on its own total outage; external monitoring
is not claimed or added.

## Manual recovery

In Actions, dispatch **Daily publication** with `batch`, `freshness`, `status` or
`rollback`. Use the same production environment. On an eligible morning, `batch`
reuses M4's bound input/identity after a transient failure. A committed result whose
response was lost is read back without a new forecast. Review the service journal:

```sh
sudo journalctl -u pf-batch.service -u pf-freshness.service --since today
sudo systemctl status pf-batch.service pf-freshness.service
```

Only rerun live publication **before session open**. An elapsed target stays missing;
never backdate publication or change the clock to make it pass. For later research,
use the existing explicit retrospective command and a distinct scientific revision
under the corresponding retained release. It cannot satisfy live freshness.
The next successful batch associates exact mature targets from its durable input
snapshot. Changed price bases remain incompatible under M4. An outcome failure can
follow a successful forecast publication; the job fails, while that result remains
visible. Inspect the run before deciding what needs recovery.

For an interrupted staged run, an operator can use M4 `resume RUN_UUID` with the
**matching bound source/lock release**, a valid restricted writer environment and
the same host lock. Do this only before the stored live deadline. Later outcome
catch-up beyond the 14-day/250-run bound uses `publish observe RUN_UUID --snapshot
LATER_HASH.json` with validated later captured inputs. See the
[existing recovery commands](PERSISTENCE_AND_PUBLICATION.md#manual-operation).
Never pass a changed release as though it were the bound scientific identity.
Administrative manual writer commands must run as `pf-batch` with the same
`flock /var/lib/pf-control/operation.lock`; inject credentials with a root-owned
systemd EnvironmentFile, not by printing or sourcing them in shared terminals.

If a release fails, inspect the error and serving revision. Automatic local
readiness recovery preserves failure status; do not report a successful release
because rollback worked. Manual `rollback` recovers the last good or previous
release and repeats readiness. If no predecessor exists, fix the initial release
and dispatch Release again. If the host rebooted mid-switch, use the administrative
console and the same gateway rollback operation. No production data is rolled back
by changing application symlinks. Root-owned service/helper changes and incompatible
future schema changes would require a separately reviewed recovery procedure.

## Retention and backup/restore

Retain all published results, input/outcome snapshots, identities and attempts;
there is no automated deletion. Retain every referenced source/lock revision, its
release manifest and the currently active, last-good and previous environments.
Review disk/database growth monthly. Remove an unreferenced failed build only under
the host lock after verifying no active process or snapshot depends on it.
Set host journald retention to at least 30 days with a size bound appropriate to
the VPS (for example `MaxRetentionSec=30day`, `SystemMaxUse=512M`), and retain
commissioning/recovery evidence separately. GitHub logs have finite retention;
copy sanitized operational evidence before it expires.

Before first live publication, configure the hosted project's backup retention
and verify its restore process. Target at least a daily protected backup, retain
seven daily and four weekly copies, and measure actual recovery time rather than
claiming an untested objective. Keep backups off the serving VPS using the
operator's existing secure backup arrangement; no additional cloud service is
introduced here. Rotate secrets independently; do not include plaintext credentials
in result artifacts or public backups. Private snapshots are sensitive datasets.

Use the established `pg_dump`/disposable `pg_restore` procedure in
[PERSISTENCE_AND_PUBLICATION.md](PERSISTENCE_AND_PUBLICATION.md#recovery-retention-and-backup).
Provision restore-target roles, validate migration checksums and snapshot hashes,
read complete results and recheck reader denials before considering restoration
successful. The full integration gate performs this real local drill. Hosted
backup entitlement/configuration, restore, RPO and RTO remain unverified.

## Commissioning evidence still required

Record the actual HTTPS URL, host and runtime versions, tested Git SHA and lock/
source hashes, service identities, certificate checks, hosted reader/writer role
checks, first complete public result, manual trigger, controlled failure/recovery,
non-root SSH restrictions and host-key mismatch rejection, host rollback, and
hosted restore results. Record **multiple actual prospective eligible sessions**
with run IDs, execution/publication/cutoff/target dates and release hashes, plus at
least one subsequently matured exact-target comparable outcome. A synthetic fixture,
retrospective backfill or manual test of the calendar is not that evidence.

Public presentation until then: “Built and locally verified a locked Python
Prophet/mean-variance demonstrator with atomic Supabase publication, a read-only
Streamlit dashboard, and VPS release/scheduling controls. Deployment and prospective
operation await commissioning. Historical evaluation found weak Prophet forecasts
against last-price baselines; no trading or profitability claim is made.”

Implementation references: [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[reusable workflow revision semantics](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
and [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
