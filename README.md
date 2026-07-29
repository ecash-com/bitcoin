## eCash Full Node

> eCash is a forked version of `bitcoin/bitcoin`. It branches off of v31.1
> and applies a series of patches. This branch is set up to run against
> `drynet3`.

### Build instructions (example uses ubuntu LTS (24.04))
Install build dependencies:
```git cmake build-essential libsqlite3-dev libboost-all-dev libzmq3-dev pkgconf```

Build:
```
cmake -B build -DBUILD_GUI=OFF -DBUILD_BENCH=OFF -DBUILD_FUZZ_BINARY=OFF -DBUILD_GUI_TESTS=OFF -DBUILD_TESTS=OFF -DENABLE_IPC=OFF -DWITH_ZMQ=ON -DBUILD_UTIL=ON
cmake --build build -j $(nproc)
```

### Directories & Config

```
// Windows: C:\Users\Username\AppData\Local\drivechain-ecash
// macOS: ~/Library/Application Support/drivechain-ecash
// Unix-like: ~/.drivechain-ecash
```
Config file name: ```drivechain-ecash.conf```


### Ports

Ports are (for now) the same as bitcoin core:
```
network 8333
rpc server 8332
```

### License
eCash (ECX) is released under the terms of the MIT license. See [COPYING](COPYING) for more
information or see https://opensource.org/license/MIT.

### Bitcoin README.md
See the regular **bitcoin** README at: https://github.com/bitcoin/bitcoin .
