#!/usr/bin/env python3
"""A crash that rolls our chain back must not turn the children of lately mined transactions into orphans.

Core flushes the chainstate every 50-70 minutes, so a node killed hard restarts where it last flushed -- blocks
behind -- and with an empty mempool. Here B's chainstate is flushed; P (fed earlier) is then mined into a B block;
C, which spends P, is fed and sits in B's mempool. B is killed (SIGKILL) and restarts one block back, where P is
neither mined nor in its mempool, and C is gone. A second eCash node, B2, still has the lost block, as peers do.
Untracked, C is simply lost. Tracked, but judged before B has caught up, C's input looks missing and C is dropped for
good. Fixed: nothing is judged until B is back at the height it had reached; then C is fed again and goes in.

Usage: test_stale_restart.py [<ecx-bitcoind>]      exit 0 = C came back, 1 = lost
"""
import os, sys, time
from bridgelib import H, Node, Pair, wait_for, result

pair = Pair("stale-restart", ecx=(sys.argv[1] if len(sys.argv) > 1 else None), base=18700,
            b_args=["-listen=1", "-bind=127.0.0.1"])
b2 = Node("B2", pair.ecx, os.path.join(pair.root, "b2"), 18705, 18706,
          ["-listen=0", f"-connect=127.0.0.1:{pair.b_p2p}", f"-ecashheight={H}", "-walletbroadcast=0"])
try:
    pair.start()
    b2.start()
    B = pair.B
    wait_for(lambda: b2.rpc("getbestblockhash") == B.rpc("getbestblockhash"), "B2 to follow B")

    c = pair.coin()
    p = pair.spend([c], [(pair.addr, c["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([p["hex"]]))
    wait_for(lambda: p["txid"] in B.mempool(), "P fed")
    B.rpc("gettxoutsetinfo", "none")                      # flush: this is where a crash will roll B back to
    h0 = B.rpc("getblockcount")
    pair.mine_ecash(1)                                    # P is mined at h0+1
    wait_for(lambda: b2.rpc("getblockcount") == h0 + 1, "B2 to have the block that will be lost")
    time.sleep(3)                                         # a pass sees P mined

    ch = pair.spend([pair.out(p)], [(pair.addr, p["vout"][0]["amount"] - 0.0001)])
    pair.wait_fed(pair.mine_bitcoin([ch["hex"]]))
    wait_for(lambda: ch["txid"] in B.mempool(), "C fed")
    print(f"P mined at {h0 + 1}, C (spends P) fed and in B's mempool; B last flushed at {h0}")

    B.kill()
    B.start()
    back = B.rpc("getblockcount")
    print(f"B killed and restarted at height {back}" + (" -- one block back, P unmined, mempool empty" if back == h0 else " (not rolled back; inconclusive)"))
    wait_for(lambda: B.rpc("getblockcount") >= h0 + 1, "B to recover the lost block from B2", timeout=120)
    ok = bool(wait_for(lambda: B.has(ch["txid"]), "C to be fed again", timeout=60))
    refed = sum(1 for l in B.log().splitlines() if "fed again after being lost" in l and " 0 fed again" not in l)
    result(back == h0 and ok, f"C {'is back' if ok else 'was lost'} after a restart {h0 + 1 - back} block(s) behind "
                              f"({refed} pass(es) fed something again)")
except AssertionError as e:
    result(False, str(e))
finally:
    b2.stop()
    pair.stop()
