# A local Hardhat chain with the escrow compiled in; the same image deploys and funds the
# demo projects (compose service chain-setup). Built from the repository root because the
# demo thresholds come from schema/thresholds.json.
FROM node:22-slim

WORKDIR /app
COPY schema schema
COPY contracts/package.json contracts/package-lock.json contracts/
RUN cd contracts && npm ci --no-audit --no-fund

COPY contracts contracts
WORKDIR /app/contracts
RUN npx hardhat compile

EXPOSE 8545
CMD ["npx", "hardhat", "node", "--hostname", "0.0.0.0", "--port", "8545"]
