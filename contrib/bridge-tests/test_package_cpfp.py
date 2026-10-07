#!/usr/bin/env python3
"""A parent below the fee floor goes in with the child that pays for it.

A zero-fee parent and its CPFP child are mined into one Bitcoin block (generateblock: no relay policy on the
Bitcoin side, as with a real package). Alone, the parent is refused "min relay fee not met" and the child then lacks
its input; both used to be lost. Offered together to ProcessNewPackage, both go in.

Usage: test_package_cpfp.py [<ecx-bitcoind>]      exit 0 = both in, 1 = lost
"""
import sys, time
from bridgelib import Pair, result

pair = Pair("package-cpfp", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18760)
try:
    pair.start()
    c = pair.coin()
    parent = pair.spend([c], [(pair.addr, c["amount"])])                                  # zero fee
    child = pair.spend([pair.out(parent)], [(pair.addr, c["amount"] - 0.001)])             # pays for both
    pair.wait_fed(pair.mine_bitcoin([parent["hex"], child["hex"]]))
    for i in range(4):
        time.sleep(4)
        if pair.present([parent["txid"], child["txid"]]) == 2:
            break
        pair.mine_ecash(1)
    n = pair.present([parent["txid"], child["txid"]])
    result(n == 2, "the zero-fee parent and its child went in together as a package" if n == 2 else f"{n}/2 arrived")
finally:
    pair.stop()
