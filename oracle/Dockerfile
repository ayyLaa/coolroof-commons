# Built from the repository root: the oracle imports contracts/shared (status codes,
# tranche order). One image runs both the HTTP server and the event listener.
FROM node:22-slim

WORKDIR /app
COPY contracts/shared contracts/shared
COPY oracle/package.json oracle/package-lock.json oracle/
RUN cd oracle && npm ci --no-audit --no-fund

COPY oracle oracle
WORKDIR /app/oracle
EXPOSE 4020
CMD ["npx", "tsx", "src/server.ts"]
