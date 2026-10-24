# CoolRoof Commons Oracle

Node.js + TypeScript bridge between backend verification results and CoolRoofEscrow.
Uses ethers v6, axios and dotenv. Node.js 20.19+ or a newer supported LTS is required.

```powershell
cd oracle
npm ci
Copy-Item .env.example .env
```

Set `BACKEND_URL`, `AMOY_RPC_URL`, `ORACLE_PRIVATE_KEY`, and `CONTRACT_ADDRESS`.
The private key must belong to the address configured by the escrow owner's
`setOracle` call. The oracle wallet needs native test tokens for gas.
The listener does not need a private key. `.env` is loaded from this folder,
independently of the working directory; existing environment variables take priority.

```powershell
npm run submit -- --roof ATH-0142 --phase quality
npm run submit -- --roof ATH-0142 --phase durability
# Start these in other terminals before submitting:
npm run listen   # forwards escrow events to the backend
npm run serve    # HTTP API for the demo panel on port 4020
```

On PowerShell, `npm.cmd run submit -- --roof ATH-0142 --phase quality` avoids
the npm.ps1 shim stripping option names. The CLI also accepts `ATH-0142 quality`
as two positional arguments to handle that shim's forwarded arguments.

Library entry point: `submitToChain(roofId, phase)` from `src/index.ts`.

## HTTP server (`npm run serve`)

The demo panel calls the oracle directly; CORS allows `ORACLE_CORS_ORIGIN`
(default `http://localhost:5173`), the port is `ORACLE_PORT` (default 4020).

- `POST /submit` with `{ "roof_id": "ATH-0142", "phase": "quality" }` returns
  `{ tx_hash, status, tranche, reason, block_number, explorer_url }`. `status` is the
  outcome below, `tranche` the tranche paid (or else held), `reason` why it was held.
  An optional `round` picks the demo round's project (`"round": 3` submits for
  `ATH-0142#3`); without it the oracle asks the backend (`GET /demo/round`) which round
  it mirrors, so the demo panel needs no round of its own.
- `GET /health` returns `{ ok, network, chain_id, contract_address, oracle_address, balance }`
  (`network` is `local`, `amoy` or `other`; the frontend shows it as a header badge) (the oracle
  balance in POL) plus `gas_price_gwei` and, for `sponsor` and `oracle`, `address`,
  `balance`, `round_cost` and `rounds_left`: how many more demo rounds each wallet can pay
  for at the current gas price. The sponsor is read as the escrow's `owner()`.

Before signing anything the oracle checks the chain: off a local chain (31337) it refuses
with `spend_not_allowed` (403), "Refusing to spend real POL on Amoy. Set
ALLOW_MAINNET_SPEND=true to proceed.", unless `ALLOW_MAINNET_SPEND=true`.

Failures come back as `{ "code": "...", "message": "..." }`, with messages written to
be shown on screen: `backend_unavailable`/`backend_http`/`backend_weather` (502),
`insufficient_gas` (503), `project_not_found` (404), `phase_already_settled`,
`project_closed` and `transaction_reverted` (409), `confirmation_unknown` (504),
`invalid_request` (422), `config` (500).
The CLI prints JSON with `transactionHash`, `blockNumber`, `outcome`, and decoded
contract events after one confirmation. Outcomes distinguish `released`, `held`,
`force_majeure`, `confirmed`, and `not_submitted`. Ordinary `flagged` and
`insufficient_data` results are not broadcast. The HTTP refusal has null `tx_hash`,
`block_number`, and `explorer_url`, with a readable reason. The only exception is an
`insufficient_data` storm submitted for durability, using the separate force-majeure code.
A successful transaction can still hold payment; the contract checks status and thresholds.

## Backend verification contract

`GET {BACKEND_URL}/verification/{encodedRoofId}` must return a flat object:

```json
{
  "roof_id": "ATH-0142",
  "status": "approved",
  "normalized_delta_c": -11.1,
  "coverage_pct": 94,
  "force_majeure": false,
  "evidence_hash": "0x1212121212121212121212121212121212121212121212121212121212121212",
  "device_signature": "0x1234"
}
```

The backend schema is maintained in `openapi.yaml`; this boundary is also validated
at runtime. `roof_id` is optional but must match if supplied.
Other fields are required; null temperatures or missing signatures are rejected
before a transaction is sent. An explicit empty signature (`0x`) is accepted by
the existing escrow, which stores signatures without authenticating a device key.

| Backend value | On-chain value |
| --- | --- |
| `approved`, `flagged`, `insufficient_data` | Status `0`, `1`, `2`; only approved ordinary results are submitted |
| `insufficient_data` with durability force majeure | Separate on-chain status `3` |
| `normalized_delta_c` | `BigInt(Math.ceil(value * 10))`; weaker cooling cannot be rounded into a pass |
| `coverage_pct` | Floored integer 0–100; 84.5 becomes 84 |
| `force_majeure` | Boolean |
| `evidence_hash` | Exactly 32 hex bytes, with optional `0x` prefix |
| `device_signature` | Even-length hex bytes, with optional `0x` prefix |
| CLI phase `quality`, `durability` | Phase `0`, `1` |

No payment thresholds are copied into this service. The escrow independently requires
approved status and its immutable numeric thresholds. The verification must also identify its measurement UUID, phase and timestamp; quality cannot be relabelled as durability. Rainfall comes directly from the same backend follow-up weather window. A force-majeure reserve payment
requires code 3 and submitted gusts above 20 m/s or precipitation above 50 mm, after
quality payment. Weather values are rounded down and still rely on oracle provenance.

## Event delivery

Events of a demo round's project (`ATH-0142#3`) reach the backend under the bare roof
ID with `"round": 3` in the body. The backend answers `409 stale_round` to any round but
the one it mirrors; the listener logs those as skipped, which is expected after every
restart, since the replay below walks through earlier rounds.

On startup the listener first replays every escrow log from `EVENTS_FROM_BLOCK`
(default 0, right for a local chain; on Amoy use the escrow's deployment block), in
chain order and 5000 blocks per request. Events emitted before the listener started,
such as the storm roof's quality payment made by `setup-demo`, still reach the backend,
which ignores events it already has.

The HTTP RPC listener polls for `TrancheReleased`, `PaymentHeld`, `ForceMajeureApplied`
and `UnreleasedReclaimed` logs and POSTs each to
`{BACKEND_URL}/contracts/{encodedRoofId}/events` in the backend's
`ContractEventCreate` shape:

```json
{
  "event_name": "PaymentHeld",
  "tranche": "QUALITY",
  "amount_wei": null,
  "tx_hash": "0x...",
  "block_number": 42,
  "reason": "Measurement thresholds not met",
  "occurred_at": "2026-07-26T08:00:00.000Z"
}
```

`tranche` is the name from `contracts/shared/tranche.ts`, `amount_wei` a decimal
string, `occurred_at` the block time. Connection failures, timeouts and 5xx answers
are retried with backoff (5 attempts, 1-8 s apart); a 4xx is the backend refusing the
event itself and is logged with the full body for manual replay, not retried. Each log
is posted once, keyed by block, transaction and log index (a force majeure transaction
emits three events with the same hash); the backend is idempotent as well. There is
no durable queue, historical backfill or reorganisation handling: start the listener
before demo transactions.

Backend HTTP and RPC calls have 10-second timeouts; receipt confirmation waits
up to 120 seconds. If confirmation is unknown after broadcast, the error includes
the transaction hash: inspect its receipt before retrying. Transactions are never
automatically resubmitted. CLI errors use English messages and a nonzero exit code;
private keys and raw axios/ethers errors are not printed.

## Checks

```powershell
npm run typecheck
npm run build
npm test
```

Tests use mock backend/RPC fixtures and do not spend tokens or require live services.
Compiled commands are `node dist/oracle/src/cli.js ...` and `node dist/oracle/src/listener.js`.

## Protected operations

Set `WRITE_API_KEY` to protect `/submit`. Outside `APP_MODE=local`, missing configuration fails closed. `EVENT_API_KEY` is sent only to the backend event-ingestion endpoint, which independently verifies the successful receipt and decoded event. Operator credentials do not authorize event injection. Use the Amoy Compose override to configure the public RPC and chain id consistently; existing deployment manifests are historical until the updated source is redeployed.
