# Built from the repository root: the types are generated from ../openapi.yaml and the
# @schema alias points at ../schema, @shared at ../contracts/shared. The build typechecks
# the tests too, and the evidence contract test imports the committed reports in
# ../data/snapshots.
FROM node:22-slim AS build

WORKDIR /app
COPY openapi.yaml openapi.yaml
COPY schema schema
COPY contracts/shared contracts/shared
COPY data/snapshots data/snapshots
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund

COPY frontend frontend
# Vite bakes these in at build time; they are the addresses the browser uses.
ARG VITE_API_URL=http://localhost:8000
ARG VITE_ORACLE_URL=http://localhost:4020
ARG VITE_AMOY_RPC_URL=http://localhost:8545
ARG VITE_CHAIN_ID=31337
ARG VITE_CONTRACT_ADDRESS=
ARG VITE_EXPLORER_URL=
ENV VITE_API_URL=$VITE_API_URL VITE_ORACLE_URL=$VITE_ORACLE_URL VITE_AMOY_RPC_URL=$VITE_AMOY_RPC_URL \
    VITE_CHAIN_ID=$VITE_CHAIN_ID VITE_EXPLORER_URL=$VITE_EXPLORER_URL VITE_CONTRACT_ADDRESS=$VITE_CONTRACT_ADDRESS
RUN cd frontend && npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 5173
