'use client'

import React from 'react'
import type { Transaction } from '@/types'

interface Props {
  transaction: Transaction | null
}

function ScoreBar({ score, color }: { score: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${score * 100}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs text-gray-300 w-10 text-right">{(score * 100).toFixed(0)}%</span>
    </div>
  )
}

function decisionStyle(decision: string) {
  switch (decision) {
    case 'APPROVE':
      return { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500', color: '#22c55e' }
    case 'REVIEW':
      return { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500', color: '#eab308' }
    case 'BLOCK':
      return { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500', color: '#ef4444' }
    default:
      return { bg: 'bg-gray-700', text: 'text-gray-400', border: 'border-gray-600', color: '#9ca3af' }
  }
}

interface StageBoxProps {
  title: string
  subtitle: string
  score: number
  color: string
  features: Record<string, number>
}

function StageBox({ title, subtitle, score, color, features }: StageBoxProps) {
  const topFeatures = Object.entries(features)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)

  return (
    <div className="bg-gray-700/50 rounded-lg p-3 border border-gray-600 flex-1">
      <div className="text-xs text-gray-400 mb-0.5">{subtitle}</div>
      <div className="text-sm font-semibold text-white mb-2">{title}</div>
      <ScoreBar score={score} color={color} />
      <div className="mt-2 space-y-1">
        {topFeatures.map(([key, val]) => (
          <div key={key} className="flex items-center justify-between text-xs">
            <span className="text-gray-400 truncate">{key.replace(/_/g, ' ')}</span>
            <span className="text-gray-300 ml-2">{val.toFixed(3)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DecisionFlow({ transaction }: Props) {
  if (!transaction) {
    return (
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 flex items-center justify-center h-64">
        <span className="text-gray-500 text-sm">Select a transaction to see the decision flow</span>
      </div>
    )
  }

  const { risk_score } = transaction
  const finalStyle = decisionStyle(risk_score.decision)

  const stageColor = (s: number) => {
    if (s < 0.3) return '#22c55e'
    if (s < 0.7) return '#eab308'
    return '#ef4444'
  }

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
      <h2 className="text-sm font-semibold text-white mb-4">Decision Pipeline</h2>

      {/* Pipeline stages */}
      <div className="flex items-stretch gap-2">
        <StageBox
          title="Rule Engine"
          subtitle="Stage 1"
          score={risk_score.stage1_score}
          color={stageColor(risk_score.stage1_score)}
          features={risk_score.stage1_features}
        />

        {/* Arrow */}
        <div className="flex items-center text-gray-500 text-xl select-none">›</div>

        <StageBox
          title="Behavioral ML"
          subtitle="Stage 2"
          score={risk_score.stage2_score}
          color={stageColor(risk_score.stage2_score)}
          features={risk_score.stage2_features}
        />

        {/* Arrow */}
        <div className="flex items-center text-gray-500 text-xl select-none">›</div>

        {/* Final decision */}
        <div
          className={`${finalStyle.bg} rounded-lg p-3 border ${finalStyle.border} flex-1 flex flex-col items-center justify-center gap-2`}
        >
          <span className="text-xs text-gray-400">Final Decision</span>
          <span className={`text-xl font-bold ${finalStyle.text}`}>{risk_score.decision}</span>
          <div className="w-full">
            <ScoreBar score={risk_score.final_score} color={finalStyle.color} />
          </div>
          <span className="text-xs text-gray-400">
            Confidence: {(risk_score.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Transaction summary */}
      <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
        <div className="bg-gray-700/40 rounded p-2">
          <div className="text-gray-400">Amount</div>
          <div className="text-white font-medium">
            ${transaction.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div className="bg-gray-700/40 rounded p-2">
          <div className="text-gray-400">Merchant</div>
          <div className="text-white font-medium truncate">{transaction.merchant}</div>
        </div>
        <div className="bg-gray-700/40 rounded p-2">
          <div className="text-gray-400">Location</div>
          <div className="text-white font-medium truncate">{transaction.location}</div>
        </div>
      </div>
    </div>
  )
}
