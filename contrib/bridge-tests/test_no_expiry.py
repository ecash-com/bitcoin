#!/usr/bin/env python3
"""A held transaction must never expire while it can still be accepted.

A 20-transaction chain is mined into one Bitcoin block and B's cluster limit (10) holds the tail.
B's clock then jumps 31 days (setmocktime) and a retry pass runs while the tail is still blocked.
A queue that gives up on anything held past 30 days drops the tail -- and the Bitcoin block is never
re-fed, so it is gone for good, although every one of those transactions was still valid. Fixed:
the tail stays held and arrives as soon as B mines.

Usage: test_no_expiry.py [<ecx-bitcoind>]      exit 0 = tail survived, 1 = lost
"""
import sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("no-expiry", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18610,
            b_args=["-limitclustercount=10"])
try:
    pair.start()
    B = pair.B
    chain = pair.chain(20)
    txids = [t["txid"] for t in chain]
    pair.wait_fed(pair.mine_bitcoin([t["hex"] for t in chain]))
    wait_for(lambda: pair.present(txids) == 10, "10 accepted with the tail held")
    print("fed: 10/20 in B's mempool, 10 held behind the cluster limit")

    # 31 days pass on B while the tail is still cluster-blocked; a retry pass must run before B mines,
    # or the tail would simply be accepted and the test would prove nothing.
    mark = len(B.log())
    B.rpc("setmocktime", int(time.time()) + 31 * 86400)
    ran = wait_for(lambda: ("re-offered held Bitcoin transactions" in B.log()[mark:]
                            or "bridge: retry pass" in B.log()[mark:]), "a retry pass after the clock jump", timeout=150)
    tail = B.log()[mark:]
    dropped_line = next((l for l in tail.splitlines() if "re-offered held" in l), "")
    print("retry pass after the jump:", (dropped_line.split("bridge: ")[-1] if dropped_line else "(nothing changed)"))

    for i in range(4):
        pair.mine_ecash(1)
        time.sleep(4)
        print(f"  after B block {i + 1}: {pair.present(txids)}/20")
        if pair.present(txids) == 20:
            break
    n = pair.present(txids)
    result(n == 20, f"{n}/20 -- the tail " + ("survived the 31-day wait" if n == 20 else f"was dropped as expired ({20 - n} lost)"))
finally:
    pair.stop()
