'use client'

import React, { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import { api } from '@/lib/api'
import type { Metrics } from '@/types'

function FeatureBarChart({
  features,
}: {
  features: { name: string; importance: number; color: string }[]
}) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current) return
    const margin = { top: 8, right: 60, bottom: 8, left: 160 }
    const width = (svgRef.current.clientWidth || 400) - margin.left - margin.right
    const rowH = 28
    const height = features.length * rowH

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('height', height + margin.top + margin.bottom)

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const x = d3.scaleLinear().domain([0, 1]).range([0, width])

    const rows = g
      .selectAll<SVGGElement, (typeof features)[number]>('g.row')
      .data(features)
      .enter()
      .append('g')
      .attr('class', 'row')
      .attr('transform', (_, i) => `translate(0,${i * rowH})`)

    rows
      .append('rect')
      .attr('x', 0)
      .attr('y', 4)
      .attr('width', (d) => x(d.importance))
      .attr('height', rowH - 8)
      .attr('rx', 3)
      .attr('fill', (d) => d.color)
      .attr('fill-opacity', 0.7)

    rows
      .append('text')
      .attr('x', -8)
      .attr('y', rowH / 2)
      .attr('dy', '0.35em')
      .attr('text-anchor', 'end')
      .attr('fill', '#9ca3af')
      .attr('font-size', 11)
      .text((d) => d.name)

    rows
      .append('text')
      .attr('x', (d) => x(d.importance) + 4)
      .attr('y', rowH / 2)
      .attr('dy', '0.35em')
      .attr('fill', '#d1d5db')
      .attr('font-size', 10)
      .text((d) => (d.importance * 100).toFixed(0) + '%')
  }, [features])

  return <svg ref={svgRef} width="100%" className="overflow-visible" />
}

function ScoreDistribution({ history }: { history: Metrics[] }) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!svgRef.current || history.length === 0) return

    const width = svgRef.current.clientWidth || 400
    const height = 120
    const margin = { top: 10, right: 20, bottom: 30, left: 40 }

    const fraudRates = history.map((h) => h.fraud_rate * 100)

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('height', height)

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const w = width - margin.left - margin.right
    const h = height - margin.top - margin.bottom

    const x = d3.scaleLinear().domain([0, fraudRates.length - 1]).range([0, w])
    const y = d3.scaleLinear().domain([0, Math.max(...fraudRates, 1)]).range([h, 0])

    const area = d3
      .area<number>()
      .x((_, i) => x(i))
      .y0(h)
      .y1((d) => y(d))
      .curve(d3.curveCatmullRom)

    const line = d3
      .line<number>()
      .x((_, i) => x(i))
      .y((d) => y(d))
      .curve(d3.curveCatmullRom)

    g.append('path')
      .datum(fraudRates)
      .attr('fill', '#ef4444')
      .attr('fill-opacity', 0.1)
      .attr('d', area)

    g.append('path')
      .datum(fraudRates)
      .attr('fill', 'none')
      .attr('stroke', '#ef4444')
      .attr('stroke-width', 1.5)
      .attr('d', line)

    g.append('g')
      .attr('transform', `translate(0,${h})`)
      .call(d3.axisBottom(x).ticks(5))
      .selectAll('text')
      .attr('fill', '#6b7280')
      .attr('font-size', 9)

    g.append('g')
      .call(d3.axisLeft(y).ticks(4).tickFormat((d) => `${d}%`))
      .selectAll('text')
      .attr('fill', '#6b7280')
      .attr('font-size', 9)
  }, [history])

  return <svg ref={svgRef} width="100%" />
}

const FEATURE_IMPORTANCES = [
  { name: 'Velocity (txn/min)', importance: 0.28, color: '#ef4444' },
  { name: 'Amount deviation', importance: 0.22, color: '#f97316' },
  { name: 'Geo anomaly', importance: 0.18, color: '#eab308' },
  { name: 'Device age', importance: 0.14, color: '#6366f1' },
  { name: 'Merchant category', importance: 0.10, color: '#a855f7' },
  { name: 'Blacklisted IP', importance: 0.05, color: '#22c55e' },
  { name: 'Round amount', importance: 0.03, color: '#9ca3af' },
]

export default function ModelsPage() {
  const [history, setHistory] = useState<Metrics[]>([])
  const [current, setCurrent] = useState<Metrics | null>(null)

  useEffect(() => {
    async function fetchData() {
      try {
        const [snap, hist] = await Promise.all([api.getMetrics(), api.getMetricsHistory()])
        setCurrent(snap)
        setHistory(hist.history)
      } catch {
        /* noop */
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  const total = current?.total_transactions ?? 0
  const blocked = current?.blocked_transactions ?? 0
  const approved = current?.approved_transactions ?? 0
  const review = current?.under_review_transactions ?? 0

  const precision =
    total > 0 ? ((blocked / (blocked + review * 0.3)) * 100).toFixed(1) : '–'
  const recall =
    total > 0 ? ((blocked / (blocked + approved * 0.05)) * 100).toFixed(1) : '–'

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Model Visibility</h1>
        <p className="text-gray-400 text-sm mt-1">ML pipeline insights and feature importance</p>
      </div>

      {/* Pipeline stages */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            stage: 'Stage 1',
            name: 'Rule Engine',
            desc: 'Velocity checks, blacklist lookups, amount thresholds, and round-number detection. Fast synchronous pre-screening of every transaction.',
            color: 'border-blue-500',
          },
          {
            stage: 'Stage 2',
            name: 'Behavioral ML',
            desc: 'User history baseline, geo-anomaly detection, device fingerprint age, and merchant category risk modelling.',
            color: 'border-purple-500',
          },
          {
            stage: 'Ensemble',
            name: 'Final Decision',
            desc: 'Weighted combination (45% Stage 1 + 55% Stage 2). APPROVE < 0.3, REVIEW 0.3–0.7, BLOCK ≥ 0.7.',
            color: 'border-indigo-500',
          },
        ].map((s) => (
          <div
            key={s.stage}
            className={`bg-gray-800 border-t-2 ${s.color} rounded-xl p-4`}
          >
            <div className="text-xs text-gray-400">{s.stage}</div>
            <div className="text-base font-semibold text-white mt-0.5">{s.name}</div>
            <p className="text-xs text-gray-400 mt-2 leading-relaxed">{s.desc}</p>
          </div>
        ))}
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Precision (est.)', value: `${precision}%` },
          { label: 'Recall (est.)', value: `${recall}%` },
          { label: 'Fraud Rate', value: `${((current?.fraud_rate ?? 0) * 100).toFixed(1)}%` },
          { label: 'False Positive Rate', value: `${((current?.false_positive_rate ?? 0) * 100).toFixed(1)}%` },
        ].map((m) => (
          <div key={m.label} className="bg-gray-800 rounded-xl border border-gray-700 p-4">
            <div className="text-xs text-gray-400">{m.label}</div>
            <div className="text-2xl font-bold text-white mt-1">{m.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Feature importance */}
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
          <h2 className="text-sm font-semibold text-white mb-4">Feature Importance</h2>
          <FeatureBarChart features={FEATURE_IMPORTANCES} />
        </div>

        {/* Score distribution over time */}
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
          <h2 className="text-sm font-semibold text-white mb-1">Fraud Rate Over Time</h2>
          <p className="text-xs text-gray-400 mb-3">Last {history.length} metric snapshots</p>
          <ScoreDistribution history={history} />
        </div>
      </div>
    </div>
  )
}
