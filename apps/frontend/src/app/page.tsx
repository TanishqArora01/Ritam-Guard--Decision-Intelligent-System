'use client'

import MetricsDashboard from '@/components/MetricsDashboard'
import TransactionStream from '@/components/TransactionStream'
import DecisionFlow from '@/components/DecisionFlow'
import { useTransactionStore } from '@/store/transactionStore'

export default function DashboardPage() {
  const selectedTransaction = useTransactionStore((s) => s.selectedTransaction)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-gray-400 text-sm mt-1">Real-time fraud detection overview</p>
      </div>

      <MetricsDashboard />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <TransactionStream />
        <DecisionFlow transaction={selectedTransaction} />
      </div>
    </div>
  )
}
