# CoolRoof Commons frontend

React 19 + TypeScript + Vite, Mantine UI, Leaflet for the map, ethers v6 for the
read-only chain check. English throughout.

## Run

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local   # then adjust, see below
npm run dev                          # http://localhost:5173
```

The app talks to three services; start them first (or use `docker compose up` from the
repository root, which runs all of them):

| Service | Default | Variable |
| --- | --- | --- |
| FastAPI backend | `http://localhost:8000` | `VITE_API_URL` |
| Oracle HTTP server (`cd oracle; npm run serve`) | `http://localhost:4020` | `VITE_ORACLE_URL` |
| Chain RPC for the independent check (optional) | none | `VITE_AMOY_RPC_URL`, `VITE_CHAIN_ID` |

`VITE_CHAIN_ID` is `80002` for Amoy (default) and `31337` for a local Hardhat node.
`VITE_EXPLORER_URL` changes the transaction links (default Amoy Polygonscan).

## Pages

- **Roof atlas** (`/`): every roof of Athens or London as its GeoJSON footprint, coloured by
  albedo, a 0-1 priority filter and a budget that highlights the highest-scoring roofs that
  fit, using the backend's `estimated_cost_eur`. The list is paged 200 roofs at a time.
- **Roof detail** (`/roofs/:id`): city thresholds, satellite evidence (8 cases with
  Bonferroni and FDR), simulated temperature series, weather at the measurement hour,
  verification with raw and normalized change side by side, evidence hash and signature.
- **Escrow** (`/contracts/:id`): tranches, amounts, hold reasons, the immutable terms, the
  event timeline, and an independent ethers read of the escrow compared with the backend.
- **Demo** (`/demo`): three scenarios run against the real services in ten steps. Simulated
  readings and a synthetic photo go to the backend. The oracle refuses ordinary unapproved
  results without a transaction; approved results and the explicit storm exception reach
  the contract. A refusal shows 0 POL paid and no explorer link. Reset calls `POST /demo/reset`
  but does not fund the new round; repeat the demo with `scripts/demo-round.sh`.

## Code layout

`api/` is the only place that fetches; `hooks/` load data; `components/` only render;
`features/` are pages; `chain/` isolates ethers; `lib/` holds pure helpers.

API types are generated, never hand-written:

```powershell
npm run gen:types    # ../openapi.yaml -> src/api/schema.d.ts
```

`src/api/types.ts` only aliases the generated schema. Verification thresholds are read by
the backend from the repository's `schema/thresholds.json`; `src/lib/config.ts` holds
interface settings only (slider range, default budget, demo pacing).

## Checks

```powershell
npm run build          # tsc + vite build
npm test               # vitest unit tests
npm run format:check   # prettier, printWidth 100
npm run mock           # Prism mock of ../openapi.yaml on port 4010, for UI work without a backend
```

## Operator access and browser validation

Operator access in the header stores the write key for this tab's session and adds it to protected POST requests. The event relay uses its own separate server-side key.

`npm run test:e2e` uses installed Chrome and the running local Docker stack. It opens and funds fresh local rounds, uploads the three real browser workflows, validates the refusal display, storm weather, network badge and unfunded-reset warning, then leaves a fresh round. It refuses non-local chains. Set `PLAYWRIGHT_CHANNEL` to another installed supported browser channel if necessary.
