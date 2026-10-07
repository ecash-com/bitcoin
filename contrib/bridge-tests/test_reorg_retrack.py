#!/usr/bin/env python3
"""A fed transaction mined here and then reorganised away is tracked again.

X is fed, then mined into a B block, so the bridge stops tracking its body. B's chain then reorganises (the block is
invalidated and replaced by an empty one): X is back in the mempool but no longer tracked. B then restarts without
mempool.dat, losing X, and Bitcoin mines Y, which spends X. Untracked, X is never fed again and Y is dropped as an
orphan. Taken back from the reorganised-away block and tracked as fed, X is fed again and Y follows.

Usage: test_reorg_retrack.py [<ecx-bitcoind>]      exit 0 = both arrived, 1 = lost
"""
import sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("reorg-retrack", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18770,
            b_args=["-persistmempool=0"])
try:
    pair.start()
    B = pair.B
    c = pair.coin()
    x = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([x["hex"]]))
    wait_for(lambda: x["txid"] in B.mempool(), "X fed")
    mined = pair.mine_ecash(1)[0]
    time.sleep(4)                                            # a pass reads the block and retires X as mined
    B.rpc("invalidateblock", mined)
    B.rpc("generateblock", pair.b_addr, [])                  # an empty block in its place: X is not mined any more
    time.sleep(5)                                            # a pass sees the reorg
    print(f"X mined, then reorganised away; X {'in' if x['txid'] in B.mempool() else 'NOT in'} B's mempool")
    B.restart()                                              # -persistmempool=0: X is lost (the bridge may re-feed it at once)
    y = pair.spend([pair.out(x)], [(pair.addr, x["vout"][0]["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([y["hex"]]))
    for i in range(5):
        time.sleep(4)
        if B.has(x["txid"]) and B.has(y["txid"]):
            break
        pair.mine_ecash(1)
    retracked = "tracked again" in B.log()
    ok = B.has(x["txid"]) and B.has(y["txid"])
    result(ok, f"X {'back' if B.has(x['txid']) else 'lost'}, Y {'in' if B.has(y['txid']) else 'dropped'}"
               + (" (re-tracked after the reorg)" if retracked else ""))
finally:
    pair.stop()
