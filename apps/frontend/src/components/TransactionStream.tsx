'use client'

import React, { useEffect } from 'react'
import { useTransactionStore } from '@/store/transactionStore'
import { transactionWS } from '@/lib/websocket'
import type { Transaction } from '@/types'

function statusColor(status: string) {
  switch (status) {
    case 'approved':
      return 'bg-green-500/20 text-green-400 border-green-500/40'
    case 'blocked':
      return 'bg-red-500/20 text-red-400 border-red-500/40'
    case 'under_review':
      return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40'
    default:
      return 'bg-gray-500/20 text-gray-400 border-gray-500/40'
  }
}

function scoreColor(score: number) {
  if (score < 0.3) return 'text-green-400'
  if (score < 0.7) return 'text-yellow-400'
  return 'text-red-400'
}

interface RowProps {
  txn: Transaction
  onSelect: () => void
}

function TransactionRow({ txn, onSelect }: RowProps) {
  return (
    <button
      onClick={onSelect}
      className="w-full text-left px-4 py-3 hover:bg-gray-700/50 border-b border-gray-700/50 animate-slide-in transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-gray-400 truncate">{txn.id}</span>
            <span
              className={`shrink-0 text-xs px-2 py-0.5 rounded-full border ${statusColor(txn.status)}`}
            >
              {txn.status.replace('_', ' ').toUpperCase()}
            </span>
          </div>
          <div className="text-sm text-gray-200 mt-0.5 truncate">
            {txn.merchant}{' '}
            <span className="text-gray-500">·</span>{' '}
            <span className="text-gray-400">{txn.user_id}</span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-semibold text-white">
            ${txn.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className={`text-xs font-mono ${scoreColor(txn.risk_score.final_score)}`}>
            {(txn.risk_score.final_score * 100).toFixed(0)}% risk
          </div>
        </div>
      </div>
    </button>
  )
}

export default function TransactionStream() {
  const { transactions, isConnected, addTransaction, setConnectionStatus, setSelectedTransaction } =
    useTransactionStore()

  useEffect(() => {
    // Initial load
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    fetch(`${apiUrl}/api/transactions?limit=20`)
      .then((r) => r.json())
      .then((data: { transactions: Transaction[] }) => {
        data.transactions.forEach((t) => addTransaction(t))
      })
      .catch(() => {})

    // WebSocket
    const removeMsg = transactionWS.onMessage((raw) => {
      try {
        const txn = JSON.parse(raw) as Transaction
        addTransaction(txn)
      } catch {
        /* ignore parse errors */
      }
    })
    const removeStatus = transactionWS.onStatus(setConnectionStatus)
    transactionWS.connect()

    return () => {
      removeMsg()
      removeStatus()
      transactionWS.disconnect()
    }
  }, [addTransaction, setConnectionStatus])

  const visible = transactions.slice(0, 20)

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <h2 className="text-sm font-semibold text-white">Live Transactions</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">{transactions.length} total</span>
          <span
            className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`}
          />
          <span className="text-xs text-gray-400">{isConnected ? 'Live' : 'Offline'}</span>
        </div>
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto max-h-[520px]">
        {visible.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
            Waiting for transactions…
          </div>
        ) : (
          visible.map((txn) => (
            <TransactionRow
              key={txn.id}
              txn={txn}
              onSelect={() => setSelectedTransaction(txn)}
            />
          ))
        )}
      </div>
    </div>
  )
}
