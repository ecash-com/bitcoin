#!/usr/bin/env python3
"""Shared regtest harness for the bridge tests.

A = vanilla Bitcoin Core 29 (the Bitcoin side, reached by B over -bitcoinpeer).
B = the eCash node under test (-ecashheight=H), fed from A's post-fork blocks.

Transactions are built on A with createrawtransaction/signrawtransactionwithwallet and mined with
generateblock, so A's own mempool policy never sees them -- exactly how a Bitcoin block arrives.
RPC goes over HTTP (batchable), not a bitcoin-cli process per call.

    pair = Pair("mytest", ecx=sys.argv[1], base=18600, b_args=["-limitclustercount=10"]).start()
    try: ...
    finally: pair.stop()
"""
import base64, hashlib, json, os, shutil, signal, subprocess, sys, time
import urllib.error, urllib.request

# The Bitcoin side: a directory holding a stock Bitcoin Core 29 bitcoind.
VAN = os.environ.get("BRIDGE_VANILLA_BIN", "")
# The eCash node under test: given on the command line, else $BRIDGE_ECX_BIN, else this tree's build.
ECX_DEFAULT = os.environ.get("BRIDGE_ECX_BIN", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "build", "bin", "bitcoind"))
REGTEST_ROOT = os.environ.get("BRIDGE_REGTEST_ROOT", "/tmp/bridge-regtest")
H = 150                      # fork height
USER, PASS = "u", "p"
REGTEST_MAGIC = "fabfb5da"   # A speaks plain regtest


class RPCError(Exception):
    def __init__(self, method, err):
        self.code, self.message = err.get("code"), err.get("message")
        super().__init__(f"{method}: {self.code} {self.message}")


class Node:
    def __init__(self, name, bitcoind, datadir, p2p, rpcport, args):
        self.name, self.bitcoind, self.datadir = name, bitcoind, datadir
        self.p2p, self.rpcport, self.args = p2p, rpcport, list(args)
        self.proc = None
        self._auth = "Basic " + base64.b64encode(f"{USER}:{PASS}".encode()).decode()

    # --- process ------------------------------------------------------------------------------
    def cmdline(self):
        return [self.bitcoind, "-regtest", f"-datadir={self.datadir}", f"-port={self.p2p}",
                f"-rpcport={self.rpcport}", f"-rpcuser={USER}", f"-rpcpassword={PASS}",
                "-printtoconsole=0", "-dnsseed=0", "-listenonion=0", "-fallbackfee=0.0001"] + self.args

    def start(self, wait=120):
        os.makedirs(self.datadir, exist_ok=True)
        self.proc = subprocess.Popen(self.cmdline(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                self.rpc("getblockchaininfo")
                return self
            except Exception:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"{self.name} exited with {self.proc.returncode}; see {self.logpath()}")
                time.sleep(0.25)
        raise RuntimeError(f"{self.name} did not come up")

    def stop(self):
        if self.proc is None:
            return
        try:
            self.rpc("stop")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=90)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc = None

    def kill(self):
        """SIGKILL: no shutdown, no flush, no mempool.dat -- a crash, an OOM kill, or a container stop that timed out."""
        if self.proc is None:
            return
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()
        self.proc = None

    def restart(self, args=None):
        self.stop()
        if args is not None:
            self.args = list(args)
        return self.start()

    # --- rpc ----------------------------------------------------------------------------------
    def _post(self, payload, path="/", timeout=600):
        req = urllib.request.Request(f"http://127.0.0.1:{self.rpcport}{path}", json.dumps(payload).encode(),
                                     {"Authorization": self._auth, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:   # Core answers an RPC error with HTTP 500 + a JSON body
            return json.loads(e.read())

    def rpc(self, method, *params, wallet=None):
        out = self._post({"jsonrpc": "1.0", "id": 0, "method": method, "params": list(params)},
                         f"/wallet/{wallet}" if wallet else "/")
        if out.get("error"):
            raise RPCError(method, out["error"])
        return out["result"]

    def try_rpc(self, method, *params, wallet=None):
        try:
            return self.rpc(method, *params, wallet=wallet), None
        except RPCError as e:
            return None, e

    def batch(self, calls, wallet=None):
        """[(method, [params])] -> [(result, error-dict-or-None)] in order."""
        if not calls:
            return []
        body = [{"jsonrpc": "1.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]
        out = self._post(body, f"/wallet/{wallet}" if wallet else "/")
        out.sort(key=lambda x: x["id"])
        return [(x["result"], x["error"]) for x in out]

    # --- helpers ------------------------------------------------------------------------------
    def logpath(self):
        return os.path.join(self.datadir, "regtest", "debug.log")

    def log(self):
        try:
            with open(self.logpath(), errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def mempool(self):
        return set(self.rpc("getrawmempool"))

    def has(self, txid):
        """In the mempool, or confirmed on the active chain. (txindex also finds a transaction in a block that was
        reorganised away; getrawtransaction reports 0 confirmations for that, so it does not count.)"""
        r, _ = self.try_rpc("getrawtransaction", txid, True)
        return r is not None and ("blockhash" not in r or r.get("confirmations", 0) > 0)


def wait_for(pred, what, timeout=120, poll=0.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            v = pred()
            if v:
                return v
        except Exception as e:
            last = e
        time.sleep(poll)
    raise AssertionError(f"timeout waiting for {what}" + (f" (last error: {last})" if last else ""))


def kill_stale(root):
    """Kill any bitcoind still running on a datadir under root (by PID, never by pattern on our own command line)."""
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "bitcoind" in cmd and f"-datadir={root}/" in cmd:
            try:
                os.kill(int(d), signal.SIGKILL)
            except OSError:
                pass


class Pair:
    def __init__(self, tag, ecx=None, base=18600, b_args=(), a_args=(), debug=("mempool",)):
        self.root = os.path.join(REGTEST_ROOT, tag)
        self.ecx = ecx or ECX_DEFAULT
        self.a_p2p, self.a_rpc, self.b_p2p, self.b_rpc = base + 1, base + 2, base + 3, base + 4
        a = ["-listen=1", "-bind=127.0.0.1", "-connect=0"] + list(a_args)
        b = ["-listen=0", "-connect=0", f"-ecashheight={H}", f"-bitcoinpeer=127.0.0.1:{self.a_p2p}",
             f"-bitcoinpeermagic={REGTEST_MAGIC}", "-txindex=1", "-walletbroadcast=0", "-logtimemicros=1"]
        b += [f"-debug={c}" for c in debug] + list(b_args)
        self.A = Node("A", os.path.join(VAN, "bitcoind"), os.path.join(self.root, "a"), self.a_p2p, self.a_rpc, a)
        self.B = Node("B", self.ecx, os.path.join(self.root, "b"), self.b_p2p, self.b_rpc, b)
        self.addr = None
        self.coins = []

    def start(self):
        if not os.path.isfile(os.path.join(VAN, "bitcoind")):
            raise SystemExit("set BRIDGE_VANILLA_BIN to a directory holding a stock Bitcoin Core 29 bitcoind")
        if not os.path.isfile(self.ecx):
            raise SystemExit(f"no eCash bitcoind at {self.ecx}; pass one as the first argument")
        kill_stale(self.root)
        shutil.rmtree(self.root, ignore_errors=True)
        self.A.start()
        self.A.rpc("createwallet", "w")
        self.addr = self.A.rpc("getnewaddress", wallet="w")
        self.A.rpc("generatetoaddress", H + 120, self.addr)
        self.B.start()
        wait_for(lambda: self.B.rpc("getblockcount") >= H - 1, "B pre-fork sync")
        self.B.rpc("createwallet", "wb")
        self.b_addr = self.B.rpc("getnewaddress", wallet="wb")
        self.B.rpc("generatetoaddress", 1, self.b_addr)
        # coins that exist on both chains and are mature on B: coinbases from the shared pre-fork blocks
        height = self.A.rpc("getblockcount")
        self.coins = sorted((u for u in self.A.rpc("listunspent", wallet="w")
                             if u["confirmations"] >= height - (H - 100) + 1),
                            key=lambda u: -u["amount"])
        # let the feed catch up with A's (empty) post-fork blocks
        self.wait_fed(self.A.rpc("getbestblockhash"))
        return self

    def stop(self):
        for n in (self.B, self.A):
            try:
                n.stop()
            except Exception:
                pass

    # --- building Bitcoin transactions ----------------------------------------------------------
    def coin(self):
        c = self.coins.pop(0)
        return {"txid": c["txid"], "vout": c["vout"], "amount": float(c["amount"]), "spk": c["scriptPubKey"]}

    def spend(self, inputs, outputs, version=2, locktime=0, sequence=None):
        """inputs: [{"txid","vout","amount","spk"}] (parents may be unconfirmed); outputs: [(addr, amount)].
        Returns {"txid","hex","vout":[{"n","amount","spk"}]}."""
        ins = [{"txid": i["txid"], "vout": i["vout"]} | ({"sequence": sequence} if sequence is not None else {})
               for i in inputs]
        outs = [{a: round(v, 8)} for a, v in outputs]
        raw = self.A.rpc("createrawtransaction", ins, outs, locktime, False)
        if version != 2:
            raw = struct_version(raw, version)
        prev = [{"txid": i["txid"], "vout": i["vout"], "scriptPubKey": i["spk"], "amount": round(i["amount"], 8)}
                for i in inputs]
        signed = self.A.rpc("signrawtransactionwithwallet", raw, prev, wallet="w")
        assert signed.get("complete"), signed
        dec = self.A.rpc("decoderawtransaction", signed["hex"])
        return {"txid": dec["txid"], "hex": signed["hex"],
                "vout": [{"n": o["n"], "amount": float(o["value"]), "spk": o["scriptPubKey"]["hex"]} for o in dec["vout"]]}

    def out(self, tx, n=0):
        o = tx["vout"][n]
        return {"txid": tx["txid"], "vout": n, "amount": o["amount"], "spk": o["spk"]}

    def chain(self, length, fee=0.0001, start=None):
        """A chain of `length` 1-in-1-out transactions, each spending the previous one's output 0."""
        prev = start or self.coin()
        txs = []
        for _ in range(length):
            t = self.spend([prev], [(self.addr, prev["amount"] - fee)])
            txs.append(t)
            prev = self.out(t)
        return txs

    def chain_fast(self, length, fee=0.0001, start=None):
        """Same as chain(), but batched: txids don't commit to witnesses, so the whole chain can be laid out
        unsigned first and signed in one batch. For chains in the thousands."""
        prev = start or self.coin()
        addr_spk = self.A.rpc("getaddressinfo", self.addr, wallet="w")["scriptPubKey"]
        raws, prevs = [], []
        for _ in range(length):
            raw = self.A.rpc("createrawtransaction", [{"txid": prev["txid"], "vout": prev["vout"]}],
                             [{self.addr: round(prev["amount"] - fee, 8)}], 0, False)
            raws.append(raw)
            prevs.append({"txid": prev["txid"], "vout": prev["vout"], "scriptPubKey": prev["spk"],
                          "amount": round(prev["amount"], 8)})
            # an unsigned segwit spend serializes without a witness, so its hash is already the txid
            txid = hashlib.sha256(hashlib.sha256(bytes.fromhex(raw)).digest()).digest()[::-1].hex()
            prev = {"txid": txid, "vout": 0, "amount": round(prev["amount"] - fee, 8), "spk": addr_spk}
        out = []
        for i in range(0, length, 500):
            res = self.A.batch([("signrawtransactionwithwallet", [raws[j], [prevs[j]]]) for j in range(i, min(i + 500, length))],
                               wallet="w")
            for r, e in res:
                assert e is None and r["complete"], (e, r)
                out.append(r["hex"])
        return out

    # --- mining ---------------------------------------------------------------------------------
    def mine_bitcoin(self, hexes):
        """Mine the given raw transactions into one Bitcoin block on A (no mempool policy). Returns the block hash."""
        return self.A.rpc("generateblock", self.addr, list(hexes))["hash"]

    def mine_ecash(self, n=1):
        return self.B.rpc("generatetoaddress", n, self.b_addr, wallet="wb")

    def wait_fed(self, block_hash, timeout=120):
        """Until B has fed the given Bitcoin block (the bridge logs every block it offers)."""
        return wait_for(lambda: f"bridge: Bitcoin block {block_hash}" in self.B.log(), f"B to feed {block_hash[:16]}",
                        timeout)

    def present(self, txids):
        return sum(self.B.has(t) for t in txids)


def struct_version(raw_hex, version):
    """Rewrite the 4-byte little-endian nVersion of an unsigned raw transaction."""
    return version.to_bytes(4, "little").hex() + raw_hex[8:]


def result(ok, msg):
    print(("RESULT: PASS - " if ok else "RESULT: FAIL - ") + msg, flush=True)
    sys.exit(0 if ok else 1)
