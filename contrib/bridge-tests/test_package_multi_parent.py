#!/usr/bin/env python3
"""A child that pays for two parents below the fee floor must go in with both.

Two zero-fee parents and one child spending an output of each -- the child's fee pays for all three
-- are mined into one Bitcoin block. Neither parent is acceptable alone, and a one-parent-one-child
package fails too: the child still lacks its other parent. Only [parent, parent, child] works, which
Core's ProcessNewPackage accepts (a child with up to 24 parents). Fixed: all three arrive.

Usage: test_package_multi_parent.py [<ecx-bitcoind>]      exit 0 = all three arrived, 1 = lost
"""
import sys, time
from bridgelib import Pair, result

pair = Pair("package-multi", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18620)
try:
    pair.start()
    c1, c2 = pair.coin(), pair.coin()
    p1 = pair.spend([c1], [(pair.addr, c1["amount"])])            # zero fee
    p2 = pair.spend([c2], [(pair.addr, c2["amount"])])            # zero fee
    child = pair.spend([pair.out(p1), pair.out(p2)], [(pair.addr, c1["amount"] + c2["amount"] - 0.002)])
    txids = [p1["txid"], p2["txid"], child["txid"]]
    pair.wait_fed(pair.mine_bitcoin([p1["hex"], p2["hex"], child["hex"]]))
    print(f"mined two zero-fee parents and their child: {pair.present(txids)}/3 on B after the feed")
    for i in range(5):
        time.sleep(5)
        n = pair.present(txids)
        print(f"  attempt {i + 1}: {n}/3")
        if n == 3:
            break
        pair.mine_ecash(1)          # a tip change re-triggers the retry pass
    n = pair.present(txids)
    pkg = [l.split("bridge: ")[-1] for l in pair.B.log().splitlines() if "in packages" in l and " 0 in packages" not in l]
    for l in pkg[:2]:
        print("   ", l)
    result(n == 3, f"{n}/3 -- " + ("both parents went in with their child" if n == 3 else "lost: no one-parent package can carry them"))
finally:
    pair.stop()
