'use client'

import React, { useState, useEffect } from 'react'
import { useTransactionStore } from '@/store/transactionStore'
import { transactionWS } from '@/lib/websocket'
import type { Transaction } from '@/types'
import { ChevronUp, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

type SortKey = keyof Pick<Transaction, 'timestamp' | 'amount' | 'status'>
type SortDir = 'asc' | 'desc'

function statusBadge(status: string) {
  const base = 'px-2 py-0.5 rounded-full text-xs font-medium border'
  switch (status) {
    case 'approved':
      return clsx(base, 'bg-green-500/15 text-green-400 border-green-500/30')
    case 'blocked':
      return clsx(base, 'bg-red-500/15 text-red-400 border-red-500/30')
    case 'under_review':
      return clsx(base, 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30')
    default:
      return clsx(base, 'bg-gray-700 text-gray-400 border-gray-600')
  }
}

export default function TransactionTable({
  onSelect,
}: {
  onSelect?: (txn: Transaction) => void
}) {
  const { transactions, addTransaction, setConnectionStatus, filter, setFilter } =
    useTransactionStore()
  const [sortKey, setSortKey] = useState<SortKey>('timestamp')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    fetch(`${apiUrl}/api/transactions?limit=100`)
      .then((r) => r.json())
      .then((data: { transactions: Transaction[] }) => {
        data.transactions.forEach((t) => addTransaction(t))
      })
      .catch(() => {})

    const removeMsg = transactionWS.onMessage((raw) => {
      try {
        const txn = JSON.parse(raw) as Transaction
        addTransaction(txn)
      } catch {
        /* noop */
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

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const filtered = transactions.filter((t) => {
    if (filter.status && t.status !== filter.status) return false
    if (t.amount < filter.minAmount) return false
    if (t.amount > filter.maxAmount) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'timestamp') cmp = a.timestamp.localeCompare(b.timestamp)
    else if (sortKey === 'amount') cmp = a.amount - b.amount
    else if (sortKey === 'status') cmp = a.status.localeCompare(b.status)
    return sortDir === 'asc' ? cmp : -cmp
  })

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return null
    return sortDir === 'asc' ? (
      <ChevronUp className="h-3 w-3" />
    ) : (
      <ChevronDown className="h-3 w-3" />
    )
  }

  const statuses = ['', 'approved', 'blocked', 'under_review']

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-gray-700">
        <select
          value={filter.status}
          onChange={(e) => setFilter({ status: e.target.value })}
          className="text-xs bg-gray-700 text-gray-300 rounded px-2 py-1 border border-gray-600"
        >
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s ? s.replace('_', ' ').toUpperCase() : 'All statuses'}
            </option>
          ))}
        </select>
        <span className="text-xs text-gray-400">{sorted.length} transactions</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 text-xs text-gray-400 uppercase">
              <th className="px-4 py-2 text-left">ID</th>
              <th
                className="px-4 py-2 text-left cursor-pointer hover:text-white"
                onClick={() => toggleSort('timestamp')}
              >
                <span className="flex items-center gap-1">
                  Time <SortIcon col="timestamp" />
                </span>
              </th>
              <th className="px-4 py-2 text-left">User</th>
              <th
                className="px-4 py-2 text-right cursor-pointer hover:text-white"
                onClick={() => toggleSort('amount')}
              >
                <span className="flex items-center justify-end gap-1">
                  Amount <SortIcon col="amount" />
                </span>
              </th>
              <th className="px-4 py-2 text-left">Merchant</th>
              <th className="px-4 py-2 text-center">Risk</th>
              <th
                className="px-4 py-2 text-center cursor-pointer hover:text-white"
                onClick={() => toggleSort('status')}
              >
                <span className="flex items-center justify-center gap-1">
                  Status <SortIcon col="status" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 100).map((txn) => (
              <tr
                key={txn.id}
                className="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer transition-colors"
                onClick={() => onSelect?.(txn)}
              >
                <td className="px-4 py-2 font-mono text-xs text-gray-400">{txn.id}</td>
                <td className="px-4 py-2 text-xs text-gray-400">
                  {new Date(txn.timestamp).toLocaleTimeString()}
                </td>
                <td className="px-4 py-2 text-gray-300">{txn.user_id}</td>
                <td className="px-4 py-2 text-right text-white font-medium">
                  ${txn.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </td>
                <td className="px-4 py-2 text-gray-300 truncate max-w-[140px]">
                  {txn.merchant}
                </td>
                <td className="px-4 py-2 text-center">
                  <span
                    className={clsx(
                      'text-xs font-mono font-semibold',
                      txn.risk_score.final_score < 0.3
                        ? 'text-green-400'
                        : txn.risk_score.final_score < 0.7
                          ? 'text-yellow-400'
                          : 'text-red-400'
                    )}
                  >
                    {(txn.risk_score.final_score * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-2 text-center">
                  <span className={statusBadge(txn.status)}>
                    {txn.status.replace('_', ' ')}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div className="text-center py-12 text-gray-500 text-sm">No transactions found</div>
        )}
      </div>
    </div>
  )
}
