#!/usr/bin/env python3
"""A Bitcoin transaction that reached our mempool by another route is watched like our own.

X is sent straight to B (sendrawtransaction) before Bitcoin mines it -- as another bridge, or ordinary relay, would
put it there. When Bitcoin's block arrives the bridge finds X already in B's mempool. Untracked, X is lost with the
mempool on a restart without mempool.dat, and Y, which spends it, then has missing inputs and is dropped. Tracked as
fed, X is fed again and Y follows.

Usage: test_known_relayed.py [<ecx-bitcoind>]      exit 0 = both arrived, 1 = lost
"""
import re, sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("known-relayed", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18710,
            b_args=["-persistmempool=0"])
try:
    pair.start()
    B = pair.B
    c = pair.coin()
    x = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    B.rpc("sendrawtransaction", x["hex"])                  # another route got there first
    pair.wait_fed(pair.mine_bitcoin([x["hex"]]))
    print("X relayed to B first; Bitcoin's block with X fed after it")
    logged = len(B.log())
    B.restart()
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
    for i in range(5):
        time.sleep(5)
        if B.has(x["txid"]) and B.has(y["txid"]):
            break
        pair.mine_ecash(1)
    ok = B.has(x["txid"]) and B.has(y["txid"])
    result(ok, "X was fed again and Y followed it" if ok else
           f"X {'back' if B.has(x['txid']) else 'lost'}, Y {'in' if B.has(y['txid']) else 'dropped'}")
finally:
    pair.stop()
