import { create } from 'zustand'
import type { Transaction } from '@/types'

interface FilterState {
  status: string
  minAmount: number
  maxAmount: number
}

interface TransactionState {
  transactions: Transaction[]
  selectedTransaction: Transaction | null
  isConnected: boolean
  filter: FilterState
  addTransaction: (txn: Transaction) => void
  setTransactions: (txns: Transaction[]) => void
  setSelectedTransaction: (txn: Transaction | null) => void
  setConnectionStatus: (status: boolean) => void
  setFilter: (filter: Partial<FilterState>) => void
}

export const useTransactionStore = create<TransactionState>((set) => ({
  transactions: [],
  selectedTransaction: null,
  isConnected: false,
  filter: { status: '', minAmount: 0, maxAmount: 100_000 },

  addTransaction: (txn) =>
    set((state) => {
      // Deduplicate by ID
      const exists = state.transactions.some((t) => t.id === txn.id)
      if (exists) return state
      return { transactions: [txn, ...state.transactions].slice(0, 500) }
    }),

  setTransactions: (txns) => set({ transactions: txns }),

  setSelectedTransaction: (txn) => set({ selectedTransaction: txn }),

  setConnectionStatus: (status) => set({ isConnected: status }),

  setFilter: (filter) =>
    set((state) => ({ filter: { ...state.filter, ...filter } })),
}))
