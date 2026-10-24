# CoolRoof Commons — Contracts

Hardhat 2, TypeScript, Solidity **0.8.24**, OpenZeppelin Ownable and ReentrancyGuard.

```powershell
cd contracts
npm ci
Copy-Item .env.example .env
npm run compile
npm run typecheck
npm test
```

Compilation generates the TypeChain types used by tests and initially downloads
the compiler. Set `PRIVATE_KEY`, `AMOY_RPC_URL`, `POLYGONSCAN_API_KEY` in `.env`
for Amoy operations (chain ID `80002`). Local tests need no key or live network.

## Escrow rules

Deploy `CoolRoofEscrow(initialOracle)`; the deployer becomes owner. Only the owner
can rotate the oracle. There is no owner withdrawal or threshold update function.

`createProject(roofId, contractor, minNormalizedDeltaCx10, minCoveragePct)` accepts
native currency and permanently fixes the project's terms. The caller is the sponsor.
Roof IDs must be unique and nonempty. Deposits must be at least 10 wei so all three
allocations are nonzero. Cooling thresholds must be negative; minimum coverage is 1–100.

Temperatures use signed tenths of a degree: `-80` means `-8.0 C`. Measurements pass
when `normalizedDeltaCx10 <= minNormalizedDeltaCx10` and `coveragePct >= minCoveragePct`.
Ordinary payments additionally require `approved` status (0). Flagged (1),
insufficient-data (2), and unknown statuses record a held decision without payment.
A separate force-majeure status (3) is only valid on the storm reserve path.
Codes live in `contracts/shared/status.ts`; tests check alignment with Solidity.

| Verification phase | Conditions | Payment |
| --- | --- | --- |
| `0` QUALITY | Approved status and both measurement thresholds pass | 60% to contractor |
| `1` DURABILITY | Approved status, quality paid, 180 days since quality payment, both thresholds pass | 30% to contractor |
| `1` with force majeure | Code 3, quality paid, gust >20 m/s or rain >50 mm; normal measurement and waiting requirements waived | Reserve to contractor; durability suspended |

Phase `2` is invalid for verification: the reserve is only paid through durability
force majeure. A settled phase cannot pay again, including switching from an
already-paid durability tranche to the reserve. Failed checks emit `PaymentHeld`
and allow a later retry. Failed recipient calls revert the entire transaction.

The reserve is the remaining 10%, including rounding dust. The durability clock starts
at the quality payment (`qualityReleasedAt`), so no durability time passes before the
coating is verified.

`reclaimUnreleased(roofId)` returns every unpaid tranche to the project's sponsor once
365 days have passed since creation: the whole deposit after a poor coating, the 30%
durability allocation after force majeure, the reserve after a normal durability
payout. It emits `UnreleasedReclaimed` and closes the project (`ProjectClosed` for any
later verification). If quality was paid late, reclaim is deferred until at least
`qualityReleasedAt + DURABILITY_DELAY + DURABILITY_CLAIM_WINDOW` (30 days). It opens at the later of that date and
creation + 365 days. Without a quality payment, the 365-day rule is unchanged.

## Evidence boundaries

`VerificationSubmitted` records the evidence hash. Files stay off chain.
`VerificationEvidence` additionally records phase, coverage, force majeure and the
device signature. **Device signatures are not cryptographically authenticated:**
no device registry, signing key or signed message format was specified. The oracle
remains trusted for measurement authenticity and weather classification; the escrow
independently enforces numeric payment rules.

`submitVerification` takes the peak gust and the precipitation in tenths
(`maxGustMsX10`, `precipMmX10`; 24.0 m/s is `240`) and reports them in
`ForceMajeureApplied`. The backend classifies the storm, and the contract requires
the separate status code and at least one weather value strictly above its limit.
Equality is insufficient. These checks do not prove weather provenance. Reflectivity is absent from the
ABI, so durability uses cooling and coverage measurements.

## Tests

Tests use local fixtures and simulated time. `contracts/test/PaymentReceiver.sol`
is only a test helper, not an application contract. Deployment and demo setup are
also exercised against the local Hardhat network.

## Deploy and fund the demo on Amoy

Fill in `.env`: `PRIVATE_KEY` funds deployment and sponsors the three projects,
`ORACLE_ADDRESS` receives verification authority, `ORACLE_PRIVATE_KEY` is its key (setup
uses it once, see below), and `CONTRACTOR_ADDRESS` receives released payments. The
sponsor wallet needs three native test tokens plus gas, the oracle wallet gas.

```powershell
npm run deploy:amoy
npm run setup-demo:amoy
```

Deployment waits for the contract, calls `setOracle`, waits for confirmation, prints
the address and saves `contracts/deployed.json` (relative to the repository root).
The manifest includes the chain ID, deployment transaction, deployer and oracle.
Do not rerun deployment to resume an existing demo; reuse its manifest.

Setup reads that manifest, verifies the connected chain and deployed code, then
creates `ATH-0142` (success), `ATH-0287` (poor coating) and `ATH-0355` (storm), the
backend's demo roof IDs, with 0.001 native test token each. The storm demo starts at the
durability recheck, which the escrow only accepts after the quality payment, so setup
pays `ATH-0355`'s quality tranche as the oracle; every other submission comes from the
oracle service.
Matching existing projects are skipped without another deposit. Conflicting
existing terms stop setup before any new deposits. A partially completed setup
can be rerun with the same addresses and manifest.

### Demo rounds

Each tranche pays once per project, so a demo can only be replayed on fresh projects.
A demo round funds its own three projects under suffixed keys, `ATH-0142#3` and so on;
the escrow is unchanged, it only sees another `roofId`. Round 0 is the unsuffixed
original. `scripts/demo-round.sh` (or `scripts/demo-round.sh amoy`) is the one command
before a recording: it opens the next round in the backend (`POST /demo/reset`) and
runs the `setup-demo` task for it:

```sh
npx hardhat setup-demo --round 3 --network amoy                 # all three roofs
npx hardhat setup-demo --round 3 --roofs ATH-0142 --network amoy # one roof
```

`deploy` and `setup-demo` refuse to send anything off a local chain unless
`ALLOW_MAINNET_SPEND=true`. `npx hardhat run scripts/round-budget.ts --network amoy` shows both wallets
and what a round costs, and fails when a full round is not affordable; `demo-round.sh`
runs it before touching the backend, and on Amoy asks for `AMOY` to be typed.

Without a manifest (the local stack's chain-setup keeps its own inside its container),
`CONTRACT_ADDRESS` names the escrow; its code is still checked. Every round costs the
sponsor three deposits plus three `createProject` calls and the oracle four
`submitVerification` calls; the oracle's `GET /health` shows how many rounds each wallet
can still pay for.

The repository's `schema/thresholds.json` (Athens) gives the demo thresholds, `-80` and `85`.
`scripts/lib/demo.ts` is shared by setup and `test/CoolRoofEscrow.test.ts`:
successful/storm quality uses `-111`, `94`; poor coating uses `-32`, `41`.
The tests move simulated time for the 180-day durability and 365-day reclaim delays.

## Local chain (the demo runs here until Amoy is funded)

Everything below was run end to end on 21 Oct: deploy, setup, the three scenarios
through the oracle, and the listener filling the backend's contract timeline. The
local node's built-in accounts stand in for the wallets: #0 deployer and sponsor
(`0xf39F...2266`), #1 oracle (`0x7099...79C8`), #2 contractor (`0x3C44...93BC`).
They are public test keys: never use them on Amoy or any public network.

```powershell
# terminal 1: the chain (starts empty on every restart)
cd contracts; npx hardhat node --hostname 127.0.0.1 --port 8545

# terminal 2: deploy and fund the three projects
cd contracts
$env:ORACLE_ADDRESS="0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
$env:CONTRACTOR_ADDRESS="0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
npx hardhat run scripts/deploy.ts --network localhost
npx hardhat run scripts/setup-demo.ts --network localhost
```

The first deployment on a fresh node is always at
`0x5FbDB2315678afecb367f032d93F642f64180aa3`. The manifest goes to
`deployed.localhost.json`, which git ignores; only Amoy's `deployed.json` is committed.
The backend needs the same addresses (`CONTRACT_ADDRESS`, `CONTRACT_SPONSOR`,
`CONTRACT_CONTRACTOR`) and the oracle needs `AMOY_RPC_URL=http://127.0.0.1:8545`,
`CONTRACT_ADDRESS` and account #1's key as `ORACLE_PRIVATE_KEY`. Environment variables
override the `.env` files, so the Amoy settings there can stay as they are.

A tranche settles once per project. Rehearse again with `scripts/demo-round.sh`,
which opens and funds new round-specific project ids; a backend reset alone does not fund them.

The recorded Amoy manifest refers to an earlier deployment. Source changes to payment
status, weather checks and reclaim timing require redeployment before public-chain use.

## Measurement freshness

`submitVerification` additionally receives `bytes32 measurementId` (the Keccak hash of the backend measurement UUID) and `uint256 measuredAt` (UTC Unix seconds). Missing identities and future timestamps cannot pay. Durability requires a different id and a later measurement than quality; ordinary durability also requires a measurement taken on or after its 180-day eligibility date. The storm exception still uses its explicit weather rules. Sponsor reclaim protects a further 30-day claim window. These checks rely on the oracle for truthful metadata and do not authenticate a physical device.
