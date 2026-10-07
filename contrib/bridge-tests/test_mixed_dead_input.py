#!/usr/bin/env python3
"""A transaction with one input we expect and one that is dead can never go in: drop it, don't hold it.

P is fed and sits in B's mempool. T spends P's output and a post-fork Bitcoin coinbase output, which never exists on
eCash (by fork+4 days a third of Bitcoin's transactions descend from one); U spends T. B reports T's inputs missing. A
rule that holds a transaction whenever one of its parents is tracked keeps T -- P is -- and re-offers it every pass
until P is mined, with U and the rest of the chain held behind it, counting toward the pause. Checked input by input,
the coinbase input is missing and untracked: T is dead, and so is U.

Usage: test_mixed_dead_input.py [<ecx-bitcoind>]      exit 0 = T and U dropped at once, 1 = held
"""
import re, sys, time
from bridgelib import H, Pair, wait_for, result

pair = Pair("mixed-dead", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18720)
try:
    pair.start()
    A, B = pair.A, pair.B
    c = pair.coin()
    p = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([p["hex"]]))
    wait_for(lambda: p["txid"] in B.mempool(), "P fed")
    tip = A.rpc("getblockcount")
    dead = next(u for u in A.rpc("listunspent", wallet="w")                  # a mature post-fork coinbase output
                if 100 <= u["confirmations"] <= tip - H + 1)
    d = {"txid": dead["txid"], "vout": dead["vout"], "amount": float(dead["amount"]), "spk": dead["scriptPubKey"]}
    t = pair.spend([pair.out(p), d], [(pair.addr, p["vout"][0]["amount"] + d["amount"] - 0.0002)])
    u = pair.spend([pair.out(t)], [(pair.addr, t["vout"][0]["amount"] - 0.0001)])
    h = pair.mine_bitcoin([t["hex"], u["hex"]])
    pair.wait_fed(h)
    line = next(l for l in B.log().splitlines() if f"bridge: Bitcoin block {h}" in l)
    print("feed:", line.split("bridge: ")[-1][:160])
    time.sleep(4)
    pair.mine_ecash(1)                                     # a pass: anything held would still be held after it
    time.sleep(4)
    held_now = [l for l in B.log().splitlines() if "still held" in l]
    last = held_now[-1].split("bridge: ")[-1] if held_now else "(no pass reported)"
    m = re.search(r"(\d+) still held", last)
    held_count = int(m.group(1)) if m else 0
    missing = int(re.search(r"(\d+) missing inputs", line).group(1))
    print("after a pass:", last[:160])
    result(missing == 2 and held_count == 0 and not B.has(t["txid"]) and not B.has(u["txid"]),
           f"T and U: {missing} dropped as dead at the feed, {held_count} held afterwards")
finally:
    pair.stop()
