#!/usr/bin/env python3
"""A version 3 child refused only because its parent's one child slot is taken waits; it is not dropped.

P (v3) and its child C1 are mined in one Bitcoin block; C2 (v3), spending another output of P, in the next. On
Bitcoin that is fine: P was mined. On eCash P and C1 may still be unconfirmed when C2 arrives, and TRUC allows a v3
transaction one unconfirmed child, so C2 could only get in by evicting its sibling C1, and pays too little to. Core
refuses it "insufficient fee (including sibling eviction)". Nothing conflicts with C2 -- it clears the moment P is
mined here -- but read as a lost conflict it is dropped for good. Held, it goes in once B mines P.

Usage: test_truc_sibling.py [<ecx-bitcoind>]      exit 0 = C2 arrived, 1 = dropped
"""
import sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("truc-sibling", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18790)
try:
    pair.start()
    A, B = pair.A, pair.B
    c = pair.coin()
    a2 = A.rpc("getnewaddress", wallet="w")
    p = pair.spend([c], [(pair.addr, 25), (a2, round(c["amount"] - 25 - 0.001, 8))], version=3)
    c1 = pair.spend([pair.out(p, 0)], [(pair.addr, 25 - 0.002)], version=3)                 # the child that pays well
    c2 = pair.spend([pair.out(p, 1)], [(pair.addr, p["vout"][1]["amount"] - 0.0001)], version=3)  # a sibling paying less
    pair.wait_fed(pair.mine_bitcoin([p["hex"], c1["hex"]]))
    wait_for(lambda: c1["txid"] in B.mempool(), "P and C1 fed")
    h = pair.mine_bitcoin([c2["hex"]])
    pair.wait_fed(h)
    line = next(l for l in B.log().splitlines() if f"bridge: Bitcoin block {h}" in l)
    print("C2's block:", line.split("bridge: ")[-1][:150])
    for i in range(4):
        pair.mine_ecash(1)                                  # mines P and C1; the next pass offers C2 again
        time.sleep(4)
        if B.has(c2["txid"]):
            break
    ok = B.has(c2["txid"])
    result(ok, "C2 waited for P to be mined, then went in" if ok else "C2 was dropped as if it had lost a conflict")
finally:
    pair.stop()
