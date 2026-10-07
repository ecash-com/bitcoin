#!/usr/bin/env python3
"""The catch-up gate does not stall the bridge when our chain will not get back to where it was.

Nothing is judged while our chain is below the height the bridge last read at (after a crash it re-syncs up to it).
Here B invalidates one of its own recent blocks: its tip drops below that height, and no header of a valid chain
reaches it any more. A gate that waits for the height for ever feeds nothing again -- here, a new Bitcoin transaction
X. Released once no known header gets back there (after a short grace for headers to arrive), it feeds X.

Usage: test_gate_release.py [<ecx-bitcoind>]      exit 0 = X arrived, 1 = the bridge stalled
"""
import sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("gate-release", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18780)
try:
    pair.start()
    B = pair.B
    hashes = pair.mine_ecash(6)
    time.sleep(4)                                            # passes read up to the tip
    B.rpc("invalidateblock", hashes[2])                      # our tip drops 4 blocks, onto a branch that ends there
    print(f"B invalidated its own block; tip now {B.rpc('getblockcount')}, 4 below where the bridge last read")
    c = pair.coin()
    x = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    pair.mine_bitcoin([x["hex"]])
    try:
        wait_for(lambda: B.has(x["txid"]), "X to be fed", timeout=200)
        ok = True
    except AssertionError:
        ok = False
    log = B.log()
    result(ok, ("X fed" if ok else "X never fed: the bridge is waiting for a height that will not come back")
               + (" (gate released)" if "reading from here" in log else ""))
finally:
    pair.stop()
