'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/api'
import type { Case } from '@/types'
import clsx from 'clsx'

const STATUSES = ['open', 'investigating', 'resolved', 'escalated'] as const
const PRIORITIES = ['low', 'medium', 'high', 'critical'] as const

function priorityColor(p: string) {
  switch (p) {
    case 'critical': return 'text-red-400 bg-red-500/10 border-red-500/30'
    case 'high': return 'text-orange-400 bg-orange-500/10 border-orange-500/30'
    case 'medium': return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'
    default: return 'text-green-400 bg-green-500/10 border-green-500/30'
  }
}

function statusColor(s: string) {
  switch (s) {
    case 'open': return 'text-blue-400 bg-blue-500/10 border-blue-500/30'
    case 'investigating': return 'text-purple-400 bg-purple-500/10 border-purple-500/30'
    case 'resolved': return 'text-green-400 bg-green-500/10 border-green-500/30'
    case 'escalated': return 'text-red-400 bg-red-500/10 border-red-500/30'
    default: return 'text-gray-400 bg-gray-700 border-gray-600'
  }
}

interface CaseCardProps {
  c: Case
  onUpdate: (id: string, data: Partial<Case>) => void
}

function CaseCard({ c, onUpdate }: CaseCardProps) {
  const [note, setNote] = useState('')

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="font-mono text-xs text-gray-400">{c.id}</span>
          <div className="text-sm text-gray-200 mt-0.5">Txn: {c.transaction_id}</div>
        </div>
        <div className="flex gap-1.5">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full border', priorityColor(c.priority))}>
            {c.priority}
          </span>
          <span className={clsx('text-xs px-2 py-0.5 rounded-full border', statusColor(c.status))}>
            {c.status}
          </span>
        </div>
      </div>

      <div className="text-xs text-gray-400 space-y-0.5">
        <div>Assigned: <span className="text-gray-300">{c.assigned_to}</span></div>
        <div>Created: {new Date(c.created_at).toLocaleString()}</div>
      </div>

      {c.notes.length > 0 && (
        <ul className="text-xs text-gray-400 space-y-1">
          {c.notes.map((n, i) => (
            <li key={i} className="border-l-2 border-gray-600 pl-2">{n}</li>
          ))}
        </ul>
      )}

      {c.resolution && (
        <div className="text-xs text-green-400 border-l-2 border-green-500 pl-2">
          Resolution: {c.resolution}
        </div>
      )}

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        <select
          value={c.status}
          onChange={(e) => onUpdate(c.id, { status: e.target.value })}
          className="text-xs bg-gray-700 text-gray-300 rounded px-2 py-1 border border-gray-600"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select
          value={c.priority}
          onChange={(e) => onUpdate(c.id, { priority: e.target.value })}
          className="text-xs bg-gray-700 text-gray-300 rounded px-2 py-1 border border-gray-600"
        >
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add note…"
          className="flex-1 text-xs bg-gray-700 text-gray-200 rounded px-2 py-1 border border-gray-600"
        />
        <button
          onClick={() => {
            if (note.trim()) {
              onUpdate(c.id, { notes: [note.trim()] })
              setNote('')
            }
          }}
          className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 rounded px-3 py-1 hover:bg-brand-500/30"
        >
          Add
        </button>
      </div>
    </div>
  )
}

export default function CasesPage() {
  const [cases, setCases] = useState<Case[]>([])
  const [filterStatus, setFilterStatus] = useState('')
  const [filterPriority, setFilterPriority] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchCases = useCallback(async () => {
    try {
      const res = await api.getCases({
        status: filterStatus || undefined,
        priority: filterPriority || undefined,
      })
      setCases(res.cases as Case[])
    } catch {
      /* noop */
    } finally {
      setLoading(false)
    }
  }, [filterStatus, filterPriority])

  useEffect(() => {
    fetchCases()
    const interval = setInterval(fetchCases, 10000)
    return () => clearInterval(interval)
  }, [fetchCases])

  async function handleUpdate(id: string, data: Partial<Case>) {
    try {
      await api.updateCase(id, data)
      await fetchCases()
    } catch {
      /* noop */
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Cases</h1>
          <p className="text-gray-400 text-sm mt-1">Analyst investigation workflow</p>
        </div>
        <div className="flex gap-2">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="text-xs bg-gray-800 text-gray-300 rounded px-2 py-1 border border-gray-700"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="text-xs bg-gray-800 text-gray-300 rounded px-2 py-1 border border-gray-700"
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-500 text-sm">Loading cases…</div>
      ) : cases.length === 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-12 text-center">
          <p className="text-gray-500 text-sm">No cases yet.</p>
          <p className="text-gray-600 text-xs mt-1">
            Cases are created from flagged transactions.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {cases.map((c) => (
            <CaseCard key={c.id} c={c} onUpdate={handleUpdate} />
          ))}
        </div>
      )}
    </div>
  )
}
