#!/usr/bin/env python3
"""A hard kill in the middle of a feed loses nothing and doubles nothing.

Five Bitcoin blocks of 20-transaction chains (ten of each held behind a cluster limit of 10) are fed back to back,
faster than the queue is written (at most once a minute), and B is killed (SIGKILL) the moment the last is fed: no
shutdown, no save, no mempool.dat. On disk the anchor is never ahead of the queue, so B re-feeds the blocks since the
last write; what it already tracks is not fed twice. All 100 arrive, and nothing is left held once they have.

Usage: test_crash_feed.py [<ecx-bitcoind>]      exit 0 = 100/100 and nothing left over, 1 = otherwise
"""
import re, sys, time
from bridgelib import Pair, wait_for, result

pair = Pair("crash-feed", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18730,
            b_args=["-limitclustercount=10"])
try:
    pair.start()
    B = pair.B
    B.rpc("gettxoutsetinfo", "none")                  # flush, so the kill rolls B back only to here
    chains = [pair.chain(20) for _ in range(5)]
    txids = [t["txid"] for c in chains for t in c]
    hashes = [pair.mine_bitcoin([t["hex"] for t in c]) for c in chains]
    pair.wait_fed(hashes[-1])
    B.kill()
    print(f"fed 5 blocks, then SIGKILL; {sum(1 for h in hashes if f'bridge: Bitcoin block {h}' in B.log())}/5 had been fed")
    B.start()
    for i in range(40):
        if pair.present(txids) == 100:
            break
        pair.mine_ecash(1)
        time.sleep(2)
    n = pair.present(txids)
    pair.mine_ecash(2)
    time.sleep(4)
    last = [l for l in B.log().splitlines() if "still held" in l][-1].split("bridge: ")[-1]
    m = re.search(r"(\d+) still held, (\d+) fed", last)
    left = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
    refed = sum(1 for h in hashes if B.log().count(f"bridge: Bitcoin block {h}") > 1)
    print(f"after restart: {n}/100 arrived; {refed} block(s) fed again; last pass: {last[:140]}")
    result(n == 100 and left == (0, 0), f"{n}/100, {left[0]} held and {left[1]} fed left over")
finally:
    pair.stop()
