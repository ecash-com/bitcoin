#!/usr/bin/env python3
"""A transaction refused for its fee is not offered again while its feerate is still under the floor.

A fan-out F (pays a fee, 200 outputs) and 200 zero-fee spends of it, one per output, all in one Bitcoin block.
F goes in; each spend is held below the relay floor, which never moves, and nothing will ever carry them.
Re-offering all 200 on every pass is the retry-cost problem again, driven by fees instead of chains -- and on a
congested mempool the whole frontier looks like this. The check compares the transaction's own feerate with the
floor and nothing else, so the answer is known without asking. Measured as the 'offered' count per pass.

Usage: test_fee_skip.py [<ecx-bitcoind>]      exit 0 = none re-offered after the first sight, 1 = re-offered
"""
import re, sys, time
from bridgelib import Pair, result

N = 200
pair = Pair("fee-skip", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18690)
try:
    pair.start()
    A, B = pair.A, pair.B
    addrs = [r for r, _ in A.batch([("getnewaddress", []) for _ in range(N + 1)], wallet="w")]
    c = pair.coin()
    raw = A.rpc("createrawtransaction", [{"txid": c["txid"], "vout": c["vout"]}],
                [{a: 0.2} for a in addrs[:N]] + [{addrs[N]: round(c["amount"] - 0.2 * N - 0.01, 8)}])
    f = A.rpc("signrawtransactionwithwallet", raw, [], wallet="w")
    fd = A.rpc("decoderawtransaction", f["hex"])
    raws = A.batch([("createrawtransaction", [[{"txid": fd["txid"], "vout": i}], [{pair.addr: 0.2}]]) for i in range(N)])
    prevs = [[{"txid": fd["txid"], "vout": i, "scriptPubKey": fd["vout"][i]["scriptPubKey"]["hex"], "amount": 0.2}] for i in range(N)]
    zs = A.batch([("signrawtransactionwithwallet", [r, p]) for (r, _), p in zip(raws, prevs)], wallet="w")
    assert all(z["complete"] for z, _ in zs)
    pair.wait_fed(pair.mine_bitcoin([f["hex"]] + [z["hex"] for z, _ in zs]))
    time.sleep(4)
    print(f"fed: F and {N} zero-fee spends of it; F {'in' if B.has(fd['txid']) else 'MISSING'}")
    offered = []
    for i in range(3):
        mark = len(B.log())
        pair.mine_ecash(1)
        time.sleep(4)
        line = next((l for l in B.log()[mark:].splitlines() if "retry pass" in l or "re-offered held" in l), "")
        m = re.search(r"\((\d+) offered", line)
        offered.append(int(m.group(1)) if m else -1)
        print(f"  pass after B block {i + 1}: {line.split('bridge: ')[-1][:120]}")
    result(max(offered) == 0, f"offered per pass {offered} for {N} held under the fee floor")
finally:
    pair.stop()
