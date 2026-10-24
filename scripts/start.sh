#!/usr/bin/env sh
# Starts the whole demo: database, backend (migrations and seed run as it starts), local
# chain with the escrow deployed and funded, oracle server and listener, frontend.
set -eu
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
fi
if ! grep -q '^DEVICE_PRIVATE_KEY=0x' .env; then
  key="0x$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')"
  sed -i.bak '/^DEVICE_PRIVATE_KEY=/d' .env && rm -f .env.bak
  echo "DEVICE_PRIVATE_KEY=$key" >> .env
  echo "Created a device signing key in .env"
fi

echo "Building and starting the stack (the first build takes a few minutes)..."
# --wait returns once every service is healthy: the backend has migrated and seeded, the
# escrow is deployed and the three demo projects are funded.
docker compose up -d --build --wait

cat <<'EOF'

CoolRoof Commons is ready.
  App       http://localhost:5173
  Demo      http://localhost:5173/demo
  API docs  http://localhost:8000/docs
  Oracle    http://localhost:4020/health

Stop: docker compose down    Start over: docker compose down -v && scripts/start.sh
EOF
