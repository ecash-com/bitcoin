#!/usr/bin/env python3
"""The retry pass must cost what can make progress, not the size of the backlog.

A 3,000-transaction chain is mined into one Bitcoin block; B's cluster limit (10) admits 10 and
holds the rest. Each B block then frees room for the next ten. A pass that re-validates every held
transaction does ~3,000 mempool acceptance attempts per block to admit ten -- each one failing on a
missing input whose parent is plainly still held. Scaled to betanet's backlog of ~170,000 that is
seconds of the message-handler thread per block. Measured here as the gap between B connecting a
block (UpdateTip) and the pass that follows it finishing ("re-offered held").

Usage: test_retry_cost.py [<ecx-bitcoind>] [chain-length]     prints per-pass cost; exit 0 always
(the verdict is the number, compared across builds)
"""
import re, statistics, sys, time
from datetime import datetime
from bridgelib import Pair, wait_for

N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
pair = Pair("retry-cost", ecx=(sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "-" else None), base=18640,
            b_args=["-limitclustercount=10"], debug=())
TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z")

def ts(line):
    m = TS.match(line)
    return datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%f").timestamp() if m else None

try:
    pair.start()
    t0 = time.time()
    hexes = pair.chain_fast(N)
    print(f"built a {N}-transaction chain in {time.time() - t0:.0f}s")
    h = pair.mine_bitcoin(hexes)
    pair.wait_fed(h, timeout=600)
    feed = next(l for l in pair.B.log().splitlines() if f"bridge: Bitcoin block {h}" in l)
    print("feed:", feed.split("bridge: ")[-1][:150])

    costs = []
    for i in range(4):
        mark = len(pair.B.log())
        pair.mine_ecash(1)
        wait_for(lambda: "re-offered held Bitcoin transactions" in pair.B.log()[mark:], "the retry pass after the block", timeout=300)
        tail = pair.B.log()[mark:].splitlines()
        tip = next(ts(l) for l in tail if "UpdateTip" in l)
        done_line = next(l for l in tail if "re-offered held Bitcoin transactions" in l)
        gap = (ts(done_line) - tip) * 1000
        own = re.search(r"([0-9.]+) ms\)", done_line)   # builds that time the pass report it themselves
        cost = float(own.group(1)) if own else gap
        costs.append(cost)
        print(f"  block {i + 1}: pass {cost:7.1f} ms ({'self-reported' if own else 'block-to-pass gap'}; gap {gap:.1f} ms)"
              f" | {done_line.split('bridge: ')[-1][:95]}")
    med = statistics.median(costs)
    print(f"RESULT: median retry pass {med:.1f} ms for ~{N} held "
          f"(~{med / N * 170000:.0f} ms of the message thread per block at betanet's ~170,000, if linear)")
finally:
    pair.stop()
