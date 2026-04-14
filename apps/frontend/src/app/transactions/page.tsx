'use client'

import React, { useState } from 'react'
import TransactionTable from '@/components/TransactionTable'
import DecisionFlow from '@/components/DecisionFlow'
import ExplainabilityPanel from '@/components/ExplainabilityPanel'
import GraphViewer from '@/components/GraphViewer'
import type { Transaction } from '@/types'

export default function TransactionsPage() {
  const [selected, setSelected] = useState<Transaction | null>(null)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Transactions</h1>
        <p className="text-gray-400 text-sm mt-1">Live transaction feed with risk scoring</p>
      </div>

      <TransactionTable onSelect={setSelected} />

      {selected && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="space-y-4">
            <DecisionFlow transaction={selected} />
            <ExplainabilityPanel transaction={selected} />
          </div>
          <GraphViewer graph={selected.graph} />
        </div>
      )}
    </div>
  )
}
