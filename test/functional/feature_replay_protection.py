#!/usr/bin/env python3
# Copyright (c) 2026 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test replay protection via the magic nLockTime.

A transaction stamped with nLockTime == LOCKTIME_THRESHOLD - 1 is treated as
final here, so it relays and confirms. Stock Bitcoin Core reads the same value
as a block height roughly 500 million blocks away and rejects the transaction
as non-final, which is what stops it replaying onto Bitcoin.
"""

from test_framework.blocktools import COINBASE_MATURITY
from test_framework.messages import SEQUENCE_FINAL
from test_framework.script import LOCKTIME_THRESHOLD
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal,
    assert_raises_rpc_error,
)
from test_framework.wallet import MiniWallet

REPLAY_LOCKTIME = LOCKTIME_THRESHOLD - 1
# nLockTime is only enforced when at least one input is non-final.
NON_FINAL_SEQUENCE = SEQUENCE_FINAL - 1


class ReplayProtectionTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        wallet = MiniWallet(node)
        self.generate(wallet, COINBASE_MATURITY + 3)

        self.log.info("A transaction with the magic nLockTime is accepted and confirms")
        tx = wallet.create_self_transfer(locktime=REPLAY_LOCKTIME, sequence=NON_FINAL_SEQUENCE)
        assert_equal(tx["tx"].nLockTime, REPLAY_LOCKTIME)
        txid = node.sendrawtransaction(tx["hex"])
        assert_equal(node.getrawmempool(), [txid])
        blockhash = self.generate(wallet, 1)[0]
        assert txid in node.getblock(blockhash)["tx"]

        self.log.info("An ordinary far-future locktime is still rejected as non-final")
        tx = wallet.create_self_transfer(locktime=REPLAY_LOCKTIME - 1, sequence=NON_FINAL_SEQUENCE)
        assert_raises_rpc_error(-26, "non-final", node.sendrawtransaction, tx["hex"])

        self.log.info("A fully final input is unaffected by the magic value")
        tx = wallet.create_self_transfer(locktime=REPLAY_LOCKTIME - 1, sequence=SEQUENCE_FINAL)
        node.sendrawtransaction(tx["hex"])


if __name__ == '__main__':
    ReplayProtectionTest(__file__).main()
