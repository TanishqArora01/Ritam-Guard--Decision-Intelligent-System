'use client'

import React, { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { Transaction, FeatureExplanation } from '@/types'

interface Props {
  transaction: Transaction | null
}

export default function ExplainabilityPanel({ transaction }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)

  const explanation: FeatureExplanation[] = transaction?.risk_score.explanation ?? []

  useEffect(() => {
    if (!svgRef.current || explanation.length === 0) return

    const margin = { top: 10, right: 80, bottom: 10, left: 160 }
    const svgEl = svgRef.current
    const totalWidth = svgEl.clientWidth || 400
    const rowH = 28
    const height = explanation.length * rowH + margin.top + margin.bottom
    const width = totalWidth - margin.left - margin.right

    const svg = d3.select(svgEl)
    svg.selectAll('*').remove()
    svg.attr('height', height + margin.top + margin.bottom)

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const maxContrib = d3.max(explanation, (d) => Math.abs(d.contribution)) ?? 0.1

    const x = d3
      .scaleLinear()
      .domain([-maxContrib, maxContrib])
      .range([0, width])

    // Zero line
    g.append('line')
      .attr('x1', x(0))
      .attr('x2', x(0))
      .attr('y1', 0)
      .attr('y2', explanation.length * rowH)
      .attr('stroke', '#4b5563')
      .attr('stroke-dasharray', '3,3')

    const rows = g
      .selectAll<SVGGElement, FeatureExplanation>('g.row')
      .data(explanation)
      .enter()
      .append('g')
      .attr('class', 'row')
      .attr('transform', (_, i) => `translate(0,${i * rowH})`)

    // Bars
    rows
      .append('rect')
      .attr('x', (d) => (d.contribution >= 0 ? x(0) : x(d.contribution)))
      .attr('y', 4)
      .attr('width', (d) => Math.abs(x(d.contribution) - x(0)))
      .attr('height', rowH - 8)
      .attr('rx', 3)
      .attr('fill', (d) => (d.contribution >= 0 ? '#ef4444' : '#22c55e'))
      .attr('fill-opacity', 0.75)

    // Feature labels
    rows
      .append('text')
      .attr('x', -8)
      .attr('y', rowH / 2)
      .attr('dy', '0.35em')
      .attr('text-anchor', 'end')
      .attr('fill', '#9ca3af')
      .attr('font-size', 11)
      .text((d) => d.feature.replace(/_/g, ' '))

    // Value labels
    rows
      .append('text')
      .attr('x', (d) => (d.contribution >= 0 ? x(d.contribution) + 4 : x(d.contribution) - 4))
      .attr('y', rowH / 2)
      .attr('dy', '0.35em')
      .attr('text-anchor', (d) => (d.contribution >= 0 ? 'start' : 'end'))
      .attr('fill', (d) => (d.contribution >= 0 ? '#f87171' : '#4ade80'))
      .attr('font-size', 10)
      .text((d) => (d.contribution >= 0 ? `+${d.contribution.toFixed(3)}` : d.contribution.toFixed(3)))
  }, [explanation])

  if (!transaction) {
    return (
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 flex items-center justify-center h-40">
        <span className="text-gray-500 text-sm">No transaction selected</span>
      </div>
    )
  }

  const topPos = explanation
    .filter((e) => e.contribution > 0)
    .slice(0, 3)
    .map((e) => `${e.feature.replace(/_/g, ' ')} (+${e.contribution.toFixed(2)})`)
    .join(', ')

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
      <h2 className="text-sm font-semibold text-white mb-1">Feature Explanations</h2>
      {topPos && (
        <p className="text-xs text-gray-400 mb-3">
          Top risk factors: <span className="text-red-400">{topPos}</span>
        </p>
      )}
      <svg ref={svgRef} width="100%" className="overflow-visible" />
    </div>
  )
}
