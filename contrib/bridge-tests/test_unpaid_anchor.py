#!/usr/bin/env python3
"""A zero-fee transaction whose fee payer can never go in is unpaid: drop it and what waits behind it, don't hold it.

T pays nothing and carries a zero-value pay-to-anchor output next to two ordinary ones -- the shape of a pre-signed
transaction whose fee is settled at broadcast. On Bitcoin, H spent the anchor and paid for both, adding a post-fork
coinbase output to cover the fee; C and D spend T's other outputs. All four are in one Bitcoin block. On eCash H can
never go in (that coinbase output never exists here), and nothing else can carry T: policy admits a transaction with
dust only at zero fee, prioritisetransaction or not, and only together with a child that spends the dust. A bridge
that holds T for its fee keeps T, C and D forever: re-offered, saved across restarts, counted in the queue. (On
betanet, 2026-10-07: 35 such transactions with 1,870 waiting behind them.)

Second, later: the fee payer H2 is held behind T2 because its other input, from Y, was still expected; then Y loses
to a conflicting eCash spend Y' and is dropped. H2 now fails its package with T2 for good, so it goes, and T2 with it.

Usage: test_unpaid_anchor.py [<ecx-bitcoind>]      exit 0 = both unpaid trees dropped, 1 = held
"""
import re, sys, time
from bridgelib import H, Pair, wait_for, result

P2A = "bcrt1pfeesnyr2tx"
pair = Pair("unpaid-anchor", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18800)
try:
    pair.start()
    A, B = pair.A, pair.B
    c = pair.coin()
    tip = A.rpc("getblockcount")
    dead = next(u for u in A.rpc("listunspent", wallet="w")                  # a mature post-fork coinbase output
                if 100 <= u["confirmations"] <= tip - H + 1)
    d = {"txid": dead["txid"], "vout": dead["vout"], "amount": float(dead["amount"]), "spk": dead["scriptPubKey"]}
    half = round(c["amount"] / 2, 8)
    t = pair.spend([c], [(pair.addr, half), (A.rpc("getnewaddress", wallet="w"), round(c["amount"] - half, 8)), (P2A, 0)],
                   version=3)
    assert t["vout"][2]["spk"] == "51024e73"
    ch = pair.spend([pair.out(t, 0)], [(pair.addr, half), (P2A, 0)], version=3)            # one level down the tree
    dd = pair.spend([pair.out(t, 1)], [(pair.addr, t["vout"][1]["amount"] - 0.0001)])      # pays its own fee
    h = pair.spend([pair.out(t, 2), d], [(pair.addr, d["amount"] - 0.0001)], version=3)    # the fee payer
    ids = {"T": t["txid"], "C": ch["txid"], "D": dd["txid"], "H": h["txid"]}
    blk = pair.mine_bitcoin([t["hex"], ch["hex"], dd["hex"], h["hex"]])
    pair.wait_fed(blk)
    line = next(l for l in B.log().splitlines() if f"bridge: Bitcoin block {blk}" in l)
    print("feed:", line.split("bridge: ")[-1][:170])
    time.sleep(4)
    pair.mine_ecash(1)                                     # a pass: anything held would still be held after it
    time.sleep(4)
    held_now = [l for l in B.log().splitlines() if "still held" in l]
    last = held_now[-1].split("bridge: ")[-1] if held_now else "(no pass reported)"
    m = re.search(r"(\d+) still held", last)
    held_count = int(m.group(1)) if m else 0
    unpaid = [l.split("bridge: ")[-1] for l in B.log().splitlines() if "fee payer can never go in" in l]
    print("after a pass:", last[:160])
    print("unpaid:", unpaid[-1][:160] if unpaid else "(none reported)")
    present = [k for k, v in ids.items() if B.has(v)]
    first = held_count == 0 and not present and len(unpaid) == 1
    print("first:", "T dropped as unpaid with C and D" if first else f"{held_count} held, in B: {present}")

    # Second: Y is fed, then replaced in B's mempool by Y' (a conflicting eCash spend of the same coin, paying more).
    k = pair.coin()
    y = pair.spend([k], [(pair.addr, k["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([y["hex"]]))
    wait_for(lambda: B.has(y["txid"]), "Y fed")
    y2 = pair.spend([k], [(A.rpc("getnewaddress", wallet="w"), k["amount"] - 0.001)])
    B.rpc("sendrawtransaction", y2["hex"])                 # eCash spent the coin differently: Y can never go in
    assert B.has(y2["txid"]) and not B.has(y["txid"])
    c2 = pair.coin()
    t2 = pair.spend([c2], [(pair.addr, half), (A.rpc("getnewaddress", wallet="w"), round(c2["amount"] - half, 8)), (P2A, 0)],
                    version=3)
    ch2 = pair.spend([pair.out(t2, 0)], [(pair.addr, half), (P2A, 0)], version=3)
    dd2 = pair.spend([pair.out(t2, 1)], [(pair.addr, t2["vout"][1]["amount"] - 0.0001)])
    h2 = pair.spend([pair.out(t2, 2), pair.out(y)], [(pair.addr, y["vout"][0]["amount"] - 0.0001)], version=3)
    ids2 = {"T2": t2["txid"], "C2": ch2["txid"], "D2": dd2["txid"], "H2": h2["txid"]}
    blk2 = pair.mine_bitcoin([t2["hex"], ch2["hex"], dd2["hex"], h2["hex"]])
    pair.wait_fed(blk2)
    line2 = next(l for l in B.log().splitlines() if f"bridge: Bitcoin block {blk2}" in l)
    print("feed:", line2.split("bridge: ")[-1][:170])
    for _ in range(60):                                    # the pass after the feed; held, it never comes
        unpaid = [l.split("bridge: ")[-1] for l in B.log().splitlines() if "fee payer can never go in" in l]
        if len(unpaid) >= 2:
            break
        time.sleep(1)
    print("unpaid:", unpaid[-1][:160] if len(unpaid) >= 2 else "(not reported)")
    pair.mine_ecash(1)
    time.sleep(4)
    present2 = [k for k, v in ids2.items() if B.has(v)]
    held_now = [l for l in B.log().splitlines() if "still held" in l]
    m = re.search(r"(\d+) still held", held_now[-1]) if held_now else None
    held2 = int(m.group(1)) if m else 0
    second = held2 == 0 and not present2 and len(unpaid) >= 2 and "and 2 waiting" in unpaid[-1]
    result(first and second, ("T, C and D dropped as unpaid at the feed; " if first else "first tree held; ") +
           ("T2, C2 and D2 dropped once H2's other input died" if second else f"second: {held2} held, in B: {present2}"))
finally:
    pair.stop()
