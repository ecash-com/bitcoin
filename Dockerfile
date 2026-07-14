FROM debian:bookworm-slim AS builder

RUN apt-get update -y \
  && apt-get install -y ca-certificates curl git gnupg gosu python3 wget build-essential cmake pkg-config libevent-dev libboost-dev libsqlite3-dev libzmq3-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /src

# Copy source files
COPY . .

# Remove any existing build directory
RUN rm -rf build/

# Run CMake to configure the build
RUN cmake -S . -B build \
        -DWITH_ZMQ=ON \
        -DENABLE_IPC=OFF \
        -DBUILD_TESTS=OFF \
        -DBUILD_UTIL:BOOL=OFF \
        -DBUILD_TX:BOOL=OFF \
        -DBUILD_WALLET_TOOL=OFF

# Build the project.
RUN cmake --build build -j"$(nproc)"

# Second stage
FROM debian:bookworm-slim

ARG UID=101
ARG GID=101

ARG TARGETPLATFORM

ENV BITCOIN_DATA=/home/bitcoin/.bitcoin
ENV PATH=/opt/bitcoin/bin:$PATH

RUN groupadd --gid ${GID} bitcoin \
  && useradd --create-home --no-log-init -u ${UID} -g ${GID} bitcoin \
  && apt-get update -y \
  && apt-get --no-install-recommends -y install jq curl gnupg gosu ca-certificates pkg-config libevent-dev libboost-dev libsqlite3-dev libzmq3-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /src/build/bin/bitcoind /opt/bitcoin/bin/bitcoind
COPY --from=builder /src/build/bin/bitcoin-cli /opt/bitcoin/bin/bitcoin-cli

COPY --chmod=755 entrypoint.sh /entrypoint.sh

VOLUME ["/home/bitcoin/.bitcoin"]

# P2P network (mainnet, testnet & regnet respectively)
EXPOSE 8333 18333 18444

# RPC interface (mainnet, testnet & regnet respectively)
EXPOSE 8332 18332 18443

# ZMQ ports (for transactions & blocks respectively)
EXPOSE 28332 28333

HEALTHCHECK --interval=300s --start-period=60s --start-interval=10s --timeout=20s CMD gosu bitcoin bitcoin-cli -datadir="$BITCOIN_DATA" -rpcwait -getinfo || exit 1

ENTRYPOINT ["/entrypoint.sh"]

RUN bitcoind -version | grep "eCash.*daemon version"

CMD ["bitcoind"]
