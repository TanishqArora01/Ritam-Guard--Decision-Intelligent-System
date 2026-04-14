import { create } from 'zustand'
import type { Metrics } from '@/types'

interface MetricsState {
  current: Metrics | null
  history: Metrics[]
  setCurrent: (m: Metrics) => void
  setHistory: (h: Metrics[]) => void
  appendHistory: (m: Metrics) => void
}

export const useMetricsStore = create<MetricsState>((set) => ({
  current: null,
  history: [],

  setCurrent: (m) => set({ current: m }),

  setHistory: (h) => set({ history: h }),

  appendHistory: (m) =>
    set((state) => ({
      current: m,
      history: [...state.history, m].slice(-60),
    })),
}))
