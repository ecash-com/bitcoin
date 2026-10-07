#!/usr/bin/env python3
"""A chain longer than B's cluster limit arrives whole.

A 40-transaction chain is mined into one Bitcoin block; B's cluster limit is 10. The mempool refuses the tail
"too-large-cluster". The shipped bridge held "too-long-mempool-chain" -- the pre-cluster-mempool string, never
emitted by this Core -- so the tail fell through to OTHER and was dropped for good, with everything later spending
it. Held and re-offered as B mines, all 40 arrive.

Usage: test_cluster_leak.py [<ecx-bitcoind>]      exit 0 = 40/40, 1 = tail lost
"""
import sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("cluster-leak", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18740,
            b_args=["-limitclustercount=10"])
try:
    pair.start()
    chain = pair.chain(40)
    txids = [t["txid"] for t in chain]
    pair.wait_fed(pair.mine_bitcoin([t["hex"] for t in chain]))
    wait_for(lambda: pair.present(txids) >= 10, "the first ten")
    print(f"fed: {pair.present(txids)}/40 accepted, the rest refused too-large-cluster")
    for i in range(6):
        pair.mine_ecash(1)
        time.sleep(3)
        n = pair.present(txids)
        print(f"  after B block {i + 1}: {n}/40")
        if n == 40:
            break
    n = pair.present(txids)
    result(n == 40, f"{n}/40 -- " + ("the whole chain arrived" if n == 40 else "the tail was dropped"))
finally:
    pair.stop()
