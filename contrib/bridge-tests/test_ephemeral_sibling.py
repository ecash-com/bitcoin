#!/usr/bin/env python3
"""A sibling of an ephemeral-dust spender must wait for the parent to confirm, not be dropped.

P pays nothing and carries a zero-value pay-to-anchor output (ephemeral dust) next to two ordinary
outputs. C1 spends the anchor and output 0 and pays for both; C2 spends only output 1. All three are
in one Bitcoin block. On eCash P is below the fee floor, so C1 carries it in as a package. C2 is then
offered with P in the mempool, and Core refuses it with "missing-ephemeral-spends": while P is
unconfirmed, every child must spend P's dust, and C1 already did. That clears the moment P confirms --
but a bridge that treats the refusal as permanent drops C2, and everything spending it, for good.

Usage: test_ephemeral_sibling.py [<ecx-bitcoind>]      exit 0 = C2 arrived after P confirmed, 1 = lost
"""
import sys, time
from bridgelib import Pair, result

P2A = "bcrt1pfeesnyr2tx"
pair = Pair("ephemeral-sibling", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18670)
try:
    pair.start()
    A, B = pair.A, pair.B
    c = pair.coin()
    addr2 = A.rpc("getnewaddress", wallet="w")
    raw = A.rpc("createrawtransaction", [{"txid": c["txid"], "vout": c["vout"]}],
                [{pair.addr: 25}, {addr2: round(c["amount"] - 25, 8)}, {P2A: 0}])
    p_hex = A.rpc("signrawtransactionwithwallet", raw, [], wallet="w")["hex"]
    pd = A.rpc("decoderawtransaction", p_hex)
    prev = lambda n: {"txid": pd["txid"], "vout": n, "scriptPubKey": pd["vout"][n]["scriptPubKey"]["hex"],
                      "amount": pd["vout"][n]["value"]}
    c1_raw = A.rpc("createrawtransaction", [{"txid": pd["txid"], "vout": 0}, {"txid": pd["txid"], "vout": 2}], [{pair.addr: 24.998}])
    c1 = A.rpc("signrawtransactionwithwallet", c1_raw, [prev(0), prev(2)], wallet="w")
    c2_raw = A.rpc("createrawtransaction", [{"txid": pd["txid"], "vout": 1}], [{pair.addr: 24.999}])
    c2 = A.rpc("signrawtransactionwithwallet", c2_raw, [prev(1)], wallet="w")
    assert c1["complete"] and c2["complete"]
    ids = {"P": pd["txid"], "C1": A.rpc("decoderawtransaction", c1["hex"])["txid"], "C2": A.rpc("decoderawtransaction", c2["hex"])["txid"]}
    pair.wait_fed(pair.mine_bitcoin([p_hex, c1["hex"], c2["hex"]]))
    time.sleep(6)
    show = lambda: ", ".join(f"{k} {'in' if B.has(v) else 'MISSING'}" for k, v in ids.items())
    print("after the feed:", show())
    for i in range(4):
        pair.mine_ecash(1)          # confirms P and C1; the pass that follows re-offers C2
        time.sleep(5)
        print(f"  after B block {i + 1}: {show()}")
        if all(B.has(v) for v in ids.values()):
            break
    refused = [l.split("bridge: ")[-1][:140] for l in B.log().splitlines() if "missing-ephemeral-spends" in l]
    print(f"  missing-ephemeral-spends seen {len(refused)}x")
    ok = all(B.has(v) for v in ids.values())
    result(ok, "C2 waited for P to confirm, then went in" if ok else "C2 was dropped although its refusal clears once P confirms")
finally:
    pair.stop()
