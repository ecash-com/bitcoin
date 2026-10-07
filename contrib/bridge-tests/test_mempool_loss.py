#!/usr/bin/env python3
"""A fed transaction that the node later loses must be fed again.

`mempool.dat` is written only on a clean shutdown, so a crash, an OOM kill or a container stop that
outruns the shutdown leaves the node with an empty mempool -- here simulated exactly with
-persistmempool=0. X is fed and accepted; B restarts and X is gone; the next Bitcoin block carries Y,
which spends X. The anchor has moved past X's block, so it is never re-fed: X is lost, Y then has
missing inputs and is dropped, and so is everything that later spends either. Fixed: fed
transactions are tracked until they confirm, and one that vanishes is offered again.

Usage: test_mempool_loss.py [<ecx-bitcoind>]      exit 0 = both arrived, 1 = lost
"""
import re, sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("mempool-loss", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18650,
            b_args=["-persistmempool=0"])
try:
    pair.start()
    B = pair.B
    c = pair.coin()
    x = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([x["hex"]]))
    wait_for(lambda: B.has(x["txid"]), "X accepted into B's mempool")
    print("X fed and in B's mempool")

    logged = len(B.log())
    B.restart()                                   # -persistmempool=0: it comes back with nothing
    if B.has(x["txid"]):
        # The bridge's first pass after startup can feed X again before we look. Then the log since the restart says
        # so; if it doesn't, the mempool survived and the test would prove nothing.
        refed = [int(n) for n in re.findall(r"(\d+) fed again after being lost", B.log()[logged:])]
        assert refed and max(refed) >= 1, "the mempool survived the restart; the test proves nothing"
        print("B restarted without its mempool; the bridge has already fed X again")
    else:
        print("B restarted without its mempool: X is gone")

    y = pair.spend([pair.out(x)], [(pair.addr, x["vout"][0]["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([y["hex"]]))
    print("Bitcoin mined Y, which spends X")
    for i in range(5):
        time.sleep(5)
        have = (B.has(x["txid"]), B.has(y["txid"]))
        print(f"  attempt {i + 1}: X {'present' if have[0] else 'MISSING'}, Y {'present' if have[1] else 'MISSING'}")
        if all(have):
            break
        pair.mine_ecash(1)
    ok = B.has(x["txid"]) and B.has(y["txid"])
    result(ok, "X was fed again and Y followed it" if ok else "X was lost with the mempool, and Y was dropped as an orphan")
finally:
    pair.stop()
