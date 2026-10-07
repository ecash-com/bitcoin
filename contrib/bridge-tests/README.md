# Bridge regtest proofs

Each test runs a regtest pair: **A**, a stock Bitcoin Core 29 node (the Bitcoin side), and **B**, the eCash node under
test, which reaches A over `-bitcoinpeer` and feeds A's post-fork blocks into its own mempool. Transactions are mined on
A with `generateblock`, so A's relay policy never sees them — exactly how a Bitcoin block arrives. Every test states the
failure it reproduces, and exits 0 only if nothing is lost.

```
BRIDGE_VANILLA_BIN=/path/to/bitcoin-29.0/bin ./run_all.py path/to/ecash/bitcoind
```

Python 3 standard library only. Datadirs go under `$BRIDGE_REGTEST_ROOT` (default `/tmp/bridge-regtest`); each test has
its own ports, so `run_all.py` runs two at a time. Pass one or more test names to run just those.

| test | what it proves | before | after |
|---|---|---|---|
| `test_cluster_leak` | a 40-tx chain behind a cluster limit of 10 arrives whole | 10/40 | 40/40 |
| `test_restart_persist` | what is held survives a restart | 10/40 | 40/40 |
| `test_package_cpfp` | a zero-fee parent goes in with the child that pays for it | 0/2 | 2/2 |
| `test_no_expiry` | a held transaction is never dropped for its age (31-day `setmocktime` jump) | 10/20 | 20/20 |
| `test_package_multi_parent` | a child paying for two zero-fee parents goes in with both | 0/3 | 3/3 |
| `test_ephemeral_sibling` | a sibling refused `missing-ephemeral-spends` waits for the dust parent to confirm | lost | in |
| `test_backpressure` | a full queue pauses the feed instead of refusing transactions; stuck ones cannot hold it paused | 63/100 | 100/100 |
| `test_fee_skip` | a transaction under the fee floor is not re-offered every pass | 200 offered/pass | 0 |
| `test_mempool_loss` | a fed transaction the node later loses (restart without `mempool.dat`) is fed again | lost | in |
| `test_known_relayed` | one that reached the mempool by another route is tracked too | lost | in |
| `test_stale_restart` | SIGKILL, restart a block behind, re-sync from a second node: children of lately-mined txs survive | lost | in |
| `test_mixed_dead_input` | a transaction with one live and one dead input is dropped at once, not held | — | dropped |
| `test_crash_feed` | SIGKILL mid-feed: blocks since the last write are re-fed, nothing lost or doubled | — | 100/100 |
| `test_reorg_retrack` | a fed transaction mined here and then reorganised away is tracked again | lost | in |
| `test_gate_release` | the catch-up gate releases when our chain will not get back to where it was | stalled | fed |
| `test_truc_sibling` | a v3 child refused only for its parent's one child slot waits, not dropped | lost | in |
| `test_unpaid_anchor` | a zero-fee anchor transaction whose fee payer can never go in is dropped with what waits behind it, at the feed and when the fee payer's other input dies later | 7 held | 0 |
| `test_retry_cost` | a pass costs what can progress, not the backlog (8,000 held) | 401 ms | ~7 ms |

"Before" is the build just before the commit that fixes it; `test_backpressure` uses that build with its limit compiled
down to 6,000 WU.
