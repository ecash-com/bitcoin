// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_NET_PROCESSING_H
#define BITCOIN_NET_PROCESSING_H

#include <consensus/amount.h>
#include <net.h>
#include <node/txorphanage.h>
#include <private_broadcast.h>
#include <protocol.h>
#include <threadsafety.h>
#include <uint256.h>
#include <util/expected.h>
#include <validationinterface.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

class AddrMan;
class CTxMemPool;
class ChainstateManager;
class BanMan;
class CBlockIndex;
class CScheduler;
class DataStream;
class uint256;

namespace node {
class Warnings;
} // namespace node

/** Whether transaction reconciliation protocol should be enabled by default. */
static constexpr bool DEFAULT_TXRECONCILIATION_ENABLE{false};
/** Default number of non-mempool transactions to keep around for block reconstruction. Includes
    orphan, replaced, and rejected transactions. */
static const uint32_t DEFAULT_BLOCK_RECONSTRUCTION_EXTRA_TXN{100};
static const bool DEFAULT_PEERBLOOMFILTERS = false;
static const bool DEFAULT_PEERBLOCKFILTERS = false;
/** Maximum number of outstanding CMPCTBLOCK requests for the same block. */
static const unsigned int MAX_CMPCTBLOCKS_INFLIGHT_PER_BLOCK = 3;
/** Number of headers sent in one getheaders result. We rely on the assumption that if a peer sends
 *  less than this number, we reached its tip. Changing this value is a protocol upgrade. */
static const unsigned int MAX_HEADERS_RESULTS = 2000;

struct CNodeStateStats {
    int nSyncHeight = -1;
    int nCommonHeight = -1;
    int m_starting_height = -1;
    std::chrono::microseconds m_ping_wait;
    std::vector<int> vHeightInFlight;
    bool m_relay_txs;
    int m_inv_to_send = 0;
    uint64_t m_last_inv_seq{0};
    CAmount m_fee_filter_received;
    uint64_t m_addr_processed = 0;
    uint64_t m_addr_rate_limited = 0;
    bool m_addr_relay_enabled{false};
    ServiceFlags their_services;
    int64_t presync_height{-1};
    std::chrono::seconds time_offset{0};
};

struct PeerManagerInfo {
    std::chrono::seconds median_outbound_time_offset{0s};
    bool ignores_incoming_txs{false};
};

/** Bridge: the Bitcoin feed pauses while the transactions held from our recent blocks weigh this much. A Bitcoin
 * block is 4 MWU, so this is a hundred blocks' worth -- about 100 MB serialized and 200-400 MB in memory at the
 * limit, on top of the mempool. Nothing is refused when it is reached; the blocks wait on the Bitcoin node. */
static constexpr uint64_t DEFAULT_BRIDGE_HELD_MAX_WEIGHT{100 * 4'000'000};
/** Bridge: a held transaction counts toward that limit for this many of our blocks. Older ones -- which may never
 * clear, like a transaction below the relay floor whose paying child is dead -- are kept, but no longer hold up the
 * feed; the age is in our blocks, so the pause still holds while our chain itself is stalled. */
static constexpr int BRIDGE_HELD_YOUNG_BLOCKS{144};

class PeerManager : public CValidationInterface, public NetEventsInterface
{
public:
    struct Options {
        //! Bridge: weight held from our last BRIDGE_HELD_YOUNG_BLOCKS blocks at which the Bitcoin feed pauses
        uint64_t bridge_held_max_weight{DEFAULT_BRIDGE_HELD_MAX_WEIGHT};
        //! Whether this node is running in -blocksonly mode
        bool ignore_incoming_txs{DEFAULT_BLOCKSONLY};
        //! Whether transaction reconciliation protocol is enabled
        bool reconcile_txs{DEFAULT_TXRECONCILIATION_ENABLE};
        //! Number of non-mempool transactions to keep around for block reconstruction. Includes
        //! orphan, replaced, and rejected transactions.
        uint32_t max_extra_txs{DEFAULT_BLOCK_RECONSTRUCTION_EXTRA_TXN};
        //! Whether all P2P messages are captured to disk
        bool capture_messages{false};
        //! Whether or not the internal RNG behaves deterministically (this is
        //! a test-only option).
        bool deterministic_rng{false};
        //! Number of headers sent in one getheaders message result (this is
        //! a test-only option).
        uint32_t max_headers_result{MAX_HEADERS_RESULTS};
        //! Whether private broadcast is used for sending transactions.
        bool private_broadcast{DEFAULT_PRIVATE_BROADCAST};
    };

    static std::unique_ptr<PeerManager> make(CConnman& connman, AddrMan& addrman,
                                             BanMan* banman, ChainstateManager& chainman,
                                             CTxMemPool& pool, node::Warnings& warnings, Options opts);
    virtual ~PeerManager() = default;

    /** Bridge: write what the Bitcoin block feed tracks. Called at shutdown, once the message handler has stopped. */
    virtual void FlushBridge() {}

    /**
     * Attempt to manually fetch block from a given peer. We must already have the header.
     *
     * @param[in]  peer_id      The peer id
     * @param[in]  block_index  The blockindex
     */
    virtual util::Expected<void, std::string> FetchBlock(NodeId peer_id, const CBlockIndex& block_index) = 0;

    /** Begin running background tasks, should only be called once */
    virtual void StartScheduledTasks(CScheduler& scheduler) = 0;

    /** Get statistics from node state */
    virtual bool GetNodeStateStats(NodeId nodeid, CNodeStateStats& stats) const = 0;

    virtual std::vector<node::TxOrphanage::OrphanInfo> GetOrphanTransactions() = 0;

    /** Get peer manager info. */
    virtual PeerManagerInfo GetInfo() const = 0;

    /** Get info about transactions currently being privately broadcast. */
    virtual std::vector<PrivateBroadcast::TxBroadcastInfo> GetPrivateBroadcastInfo() const = 0;

    /**
     * Abort private broadcast attempts for transactions currently being privately broadcast.
     *
     * @param[in] id A transaction identifier. It will be matched against both txid and wtxid for
     *               all transactions in the private broadcast queue.
     *
     * @return Transactions removed from the private broadcast queue. If the provided id matches a
     *         txid that corresponds to multiple transactions with different wtxids, multiple
     *         transactions may be returned.
     */
    virtual std::vector<CTransactionRef> AbortPrivateBroadcast(const uint256& id) = 0;

    /**
     * Initiate a transaction broadcast to eligible peers.
     * Queue the witness transaction id to `Peer::TxRelay::m_tx_inventory_to_send`
     * for each peer. Later, depending on `Peer::TxRelay::m_next_inv_send_time` and if
     * the transaction is in the mempool, an `INV` about it may be sent to the peer.
     */
    virtual void InitiateTxBroadcastToAll(const Txid& txid, const Wtxid& wtxid) = 0;

    /**
     * Initiate a private transaction broadcast. This is done
     * asynchronously via short-lived connections to peers on privacy networks.
     */
    virtual void InitiateTxBroadcastPrivate(const CTransactionRef& tx) = 0;

    /** Send ping message to all peers */
    virtual void SendPings() = 0;

    /** Set the height of the best block and its time (seconds since epoch). */
    virtual void SetBestBlock(int height, std::chrono::seconds time) = 0;

    /* Public for unit testing. */
    virtual void UnitTestMisbehaving(NodeId peer_id) = 0;

    /**
     * Evict extra outbound peers. If we think our tip may be stale, connect to an extra outbound.
     * Public for unit testing.
     */
    virtual void CheckForStaleTipAndEvictPeers() = 0;

    /** This function is used for testing the stale tip eviction logic, see denialofservice_tests.cpp */
    virtual void UpdateLastBlockAnnounceTime(NodeId node, int64_t time_in_seconds) = 0;

    /**
     * Gets the set of service flags which are "desirable" for a given peer.
     *
     * These are the flags which are required for a peer to support for them
     * to be "interesting" to us, ie for us to wish to use one of our few
     * outbound connection slots for or for us to wish to prioritize keeping
     * their connection around.
     *
     * Relevant service flags may be peer- and state-specific in that the
     * version of the peer may determine which flags are required (eg in the
     * case of NODE_NETWORK_LIMITED where we seek out NODE_NETWORK peers
     * unless they set NODE_NETWORK_LIMITED and we are out of IBD, in which
     * case NODE_NETWORK_LIMITED suffices).
     *
     * Thus, generally, avoid calling with 'services' == NODE_NONE, unless
     * state-specific flags must absolutely be avoided. When called with
     * 'services' == NODE_NONE, the returned desirable service flags are
     * guaranteed to not change dependent on state - ie they are suitable for
     * use when describing peers which we know to be desirable, but for which
     * we do not have a confirmed set of service flags.
    */
    virtual ServiceFlags GetDesirableServiceFlags(ServiceFlags services) const = 0;
};

#endif // BITCOIN_NET_PROCESSING_H
