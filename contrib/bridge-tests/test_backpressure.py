#!/usr/bin/env python3
"""Nothing held is turned away when the queue is full: the feed pauses, and resumes as it drains. And what can
never clear does not hold the feed paused for ever.

Phase 1. The held-weight limit is 6,000 WU and B's cluster limit 10. Five Bitcoin blocks each carry a
20-transaction chain, so ten of each are held (~4,400 WU a block). A queue that turns newcomers away once full
refuses part of block 2's tail, and with it the rest of that chain; blocks 3-5 likewise. With back-pressure the
feed stops after block 2, resumes as B mines the held chains in, and all 100 arrive.

Phase 2. Twenty zero-fee transactions that nothing will ever pay for push the held weight past the limit and
pause the feed, so a later Bitcoin block with an ordinary transaction X waits. After BRIDGE_HELD_YOUNG_BLOCKS of
B's blocks they stop counting toward the pause (they are kept, with a warning), the feed resumes, and X arrives.

Usage: test_backpressure.py [<ecx-bitcoind>] [--compiled-cap]
  --compiled-cap: the binary has the 6,000 WU limit built in (the before case), so -bridgeheldmaxweight is not passed
exit 0 = nothing lost and the feed never stuck, 1 = otherwise
"""
import sys, time
from bridgelib import Pair, wait_for, result

LIMIT, YOUNG = 6000, 144
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
compiled = "--compiled-cap" in sys.argv
b_args = ["-limitclustercount=10"] + ([] if compiled else [f"-bridgeheldmaxweight={LIMIT}"])
pair = Pair("backpressure", ecx=(argv[0] if argv else None), base=18680, b_args=b_args)
try:
    pair.start()
    B = pair.B
    # ---- phase 1 --------------------------------------------------------------------------------------------
    chains = [pair.chain(20) for _ in range(5)]
    txids = [t["txid"] for c in chains for t in c]
    for c in chains:
        pair.mine_bitcoin([t["hex"] for t in c])
    print(f"phase 1: five Bitcoin blocks of 20-transaction chains; cluster limit 10, held limit {LIMIT} WU")
    for i in range(40):
        if pair.present(txids) == 100:
            break
        pair.mine_ecash(1)
        time.sleep(2)
    n1 = pair.present(txids)
    log = B.log()
    print(f"  {n1}/100 arrived after {i} B blocks; feed paused {log.count('pausing the Bitcoin feed')}x, "
          f"transactions turned away {log.count('is NOT fed')}")
    ok1 = n1 == 100

    # ---- phase 2 --------------------------------------------------------------------------------------------
    mark = len(B.log())
    stuck = []
    for _ in range(20):
        c = pair.coin()
        stuck.append(pair.spend([c], [(pair.addr, c["amount"])]))           # zero fee, no child: never clears
    pair.mine_bitcoin([z["hex"] for z in stuck])
    time.sleep(8)
    c = pair.coin()
    x = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    pair.mine_bitcoin([x["hex"]])
    time.sleep(8)
    waited = not B.has(x["txid"])
    print(f"phase 2: 20 zero-fee transactions held; X {'waits behind the pause' if waited else 'arrived at once (no pause)'}")
    pair.mine_ecash(YOUNG + 1)                                              # they age past the young window
    ok2 = bool(wait_for(lambda: B.has(x["txid"]), "X to arrive once the stuck ones age out", timeout=90))
    tail = B.log()[mark:]
    print(f"  after {YOUNG + 1} B blocks: X {'arrived' if ok2 else 'still waiting'}; "
          f"resumed {tail.count('resuming the Bitcoin feed')}x; parked warning {tail.count('without clearing')}x")
    result(ok1 and ok2, f"phase 1 {n1}/100, phase 2 X {'arrived' if ok2 else 'stuck'}")
finally:
    pair.stop()
