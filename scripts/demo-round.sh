#!/usr/bin/env sh
# Starts a fresh demo round: run this once before every recording or jury run. Each escrow
# tranche pays once per project, so a rerun needs new projects: the backend returns the
# three demo roofs to the seed and opens round N, then setup-demo funds that round's
# projects on chain (ATH-0142#N, ATH-0287#N, ATH-0355#N). The demo panel and the oracle
# pick up round N by themselves.
#
#   scripts/demo-round.sh         the local stack (scripts/start.sh)
#   scripts/demo-round.sh amoy    Amoy, with contracts/.env and contracts/deployed.json
#
# Both wallets are checked before anything changes: a round that runs out of POL halfway
# leaves the backend on a round the chain cannot pay. On Amoy, where faucet POL is spent,
# the round only starts after AMOY is typed.
set -eu
cd "$(dirname "$0")/.."

NETWORK="${1:-local}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
ORACLE_URL="${ORACLE_URL:-http://localhost:4020}"
CONFIRMATION_WORD="AMOY"
# The local stack's escrow and parties (docker-compose.yml); the chain's own test accounts sign.
LOCAL_RPC_URL="http://localhost:8545"
LOCAL_CONTRACT_ADDRESS="0x5FbDB2315678afecb367f032d93F642f64180aa3"
LOCAL_CONTRACTOR_ADDRESS="0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"

case "$NETWORK" in
  local|amoy) ;;
  *) echo "Usage: scripts/demo-round.sh [local|amoy]" >&2; exit 2 ;;
esac

# Runs a contracts hardhat task on the chosen network.
hardhat_task() {
  if [ "$NETWORK" = "local" ]; then
    (cd contracts && CHAIN_RPC_URL="${CHAIN_RPC_URL:-$LOCAL_RPC_URL}" \
      CONTRACT_ADDRESS="${CONTRACT_ADDRESS:-$LOCAL_CONTRACT_ADDRESS}" \
      CONTRACTOR_ADDRESS="${CONTRACTOR_ADDRESS:-$LOCAL_CONTRACTOR_ADDRESS}" \
      npx hardhat "$@" --network docker)
  else
    (cd contracts && npx hardhat "$@" --network amoy)
  fi
}

echo "Checking both wallets on $NETWORK before anything changes..."
if ! hardhat_task run scripts/round-budget.ts; then
  echo "Nothing was started: the backend round is unchanged and no transaction was sent." >&2
  exit 1
fi

if [ "$NETWORK" = "amoy" ]; then
  echo
  echo "This spends POL on Amoy: three deposits and setup transactions from the sponsor,"
  echo "and the storm roof's quality payment from the oracle."
  if [ ! -t 0 ]; then
    echo "Not an interactive terminal, so $CONFIRMATION_WORD cannot be typed. Nothing was started." >&2
    exit 1
  fi
  printf 'Type %s to continue: ' "$CONFIRMATION_WORD"
  read -r answer || answer=""
  if [ "$answer" != "$CONFIRMATION_WORD" ]; then
    echo "Confirmation not given. Nothing was started." >&2
    exit 1
  fi
fi

echo "Opening a new demo round in the backend ($BACKEND_URL)..."
response="$(curl -fsS -H "X-API-Key: ${WRITE_API_KEY:-}" -X POST "$BACKEND_URL/demo/reset")" || {
  echo "The backend did not answer POST /demo/reset. Is the stack running?" >&2
  exit 1
}
round="$(printf '%s' "$response" | sed -n 's/.*"round":[[:space:]]*\([0-9][0-9]*\).*/\1/p')"
if [ -z "$round" ]; then
  echo "The backend's reply has no round number: $response" >&2
  exit 1
fi
echo "Backend is on round $round; funding its projects on $NETWORK..."

# The typed confirmation above is the consent setup-demo's spend guard asks for; a local
# chain needs none.
if [ "$NETWORK" = "amoy" ]; then export ALLOW_MAINNET_SPEND=true; fi
if ! hardhat_task setup-demo --round "$round"; then
  echo "Round $round is open in the backend but not funded on chain. Fund the wallets" >&2
  echo "(GET $ORACLE_URL/health shows what a round costs) and run this script again." >&2
  exit 1
fi

health="$(curl -fsS "$ORACLE_URL/health" 2>/dev/null || true)"
sponsor_rounds="$(printf '%s' "$health" | sed -n 's/.*"sponsor":{[^}]*"rounds_left":\([0-9][0-9]*\).*/\1/p')"
oracle_rounds="$(printf '%s' "$health" | sed -n 's/.*"oracle":{[^}]*"rounds_left":\([0-9][0-9]*\).*/\1/p')"

cat <<EOF

Demo round $round is ready.
  Projects   ATH-0142#$round, ATH-0287#$round, ATH-0355#$round (storm quality already paid)
  Demo       http://localhost:5173/demo
EOF
if [ -n "$sponsor_rounds" ]; then
  echo "  Budget     sponsor can fund $sponsor_rounds more round(s), oracle can submit for $oracle_rounds"
fi
