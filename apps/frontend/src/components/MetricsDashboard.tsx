'use client'

import React, { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { useMetricsStore } from '@/store/metricsStore'
import type { Metrics } from '@/types'

interface MetricCardProps {
  label: string
  value: string
  history: number[]
  color: string
  unit?: string
}

function Sparkline({
  data,
  color,
  width = 120,
  height = 36,
}: {
  data: number[]
  color: string
  width?: number
  height?: number
}) {
  const ref = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!ref.current || data.length < 2) return
    const svg = d3.select(ref.current)
    svg.selectAll('*').remove()

    const x = d3.scaleLinear().domain([0, data.length - 1]).range([0, width])
    const y = d3
      .scaleLinear()
      .domain([d3.min(data) ?? 0, d3.max(data) ?? 1])
      .range([height - 2, 2])

    const area = d3
      .area<number>()
      .x((_, i) => x(i))
      .y0(height)
      .y1((d) => y(d))
      .curve(d3.curveCatmullRom)

    const line = d3
      .line<number>()
      .x((_, i) => x(i))
      .y((d) => y(d))
      .curve(d3.curveCatmullRom)

    svg
      .append('path')
      .datum(data)
      .attr('fill', color)
      .attr('fill-opacity', 0.15)
      .attr('d', area)

    svg
      .append('path')
      .datum(data)
      .attr('fill', 'none')
      .attr('stroke', color)
      .attr('stroke-width', 1.5)
      .attr('d', line)
  }, [data, color, width, height])

  return <svg ref={ref} width={width} height={height} />
}

function MetricCard({ label, value, history, color, unit }: MetricCardProps) {
  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <span className="text-xs text-gray-400 uppercase tracking-wide">{label}</span>
      </div>
      <div className="flex items-end justify-between">
        <span className="text-2xl font-bold text-white">
          {value}
          {unit && <span className="text-sm text-gray-400 ml-1">{unit}</span>}
        </span>
        <Sparkline data={history} color={color} />
      </div>
    </div>
  )
}

export default function MetricsDashboard() {
  const { current, history, setCurrent, setHistory } = useMetricsStore()

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>

    async function fetchMetrics() {
      try {
        const [snap, hist] = await Promise.all([
          fetch(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/metrics`).then(
            (r) => r.json() as Promise<Metrics>
          ),
          fetch(
            `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/metrics/history`
          ).then((r) => r.json() as Promise<{ history: Metrics[] }>),
        ])
        setCurrent(snap)
        setHistory(hist.history ?? [])
      } catch {
        // silently ignore fetch errors while backend is starting
      }
    }

    fetchMetrics()
    interval = setInterval(fetchMetrics, 2000)
    return () => clearInterval(interval)
  }, [setCurrent, setHistory])

  const tpsHistory = history.map((h) => h.tps)
  const latencyHistory = history.map((h) => h.latency_p95)
  const fraudHistory = history.map((h) => h.fraud_rate * 100)
  const fprHistory = history.map((h) => h.false_positive_rate * 100)

  const fmt = (n: number | undefined, decimals = 1) =>
    n !== undefined ? n.toFixed(decimals) : '–'

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <MetricCard
        label="Transactions / sec"
        value={fmt(current?.tps)}
        history={tpsHistory}
        color="#6366f1"
      />
      <MetricCard
        label="Latency p95"
        value={fmt(current?.latency_p95)}
        unit="ms"
        history={latencyHistory}
        color="#f97316"
      />
      <MetricCard
        label="Fraud Rate"
        value={fmt((current?.fraud_rate ?? 0) * 100)}
        unit="%"
        history={fraudHistory}
        color="#ef4444"
      />
      <MetricCard
        label="False Positive Rate"
        value={fmt((current?.false_positive_rate ?? 0) * 100)}
        unit="%"
        history={fprHistory}
        color="#eab308"
      />
    </div>
  )
}
