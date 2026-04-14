'use client';

import React, { useMemo } from 'react';
import { forceCenter, forceLink, forceManyBody, forceSimulation } from 'd3-force';
import type { FraudGraph } from '../lib/types';
import { GlassPanel, SectionHeader } from './cockpit';

type NodeDatum = {
  id: string;
  label: string;
  kind: string;
  risk: number;
  x?: number;
  y?: number;
};

type LinkDatum = {
  source: string | NodeDatum;
  target: string | NodeDatum;
  relation: string;
  strength: number;
};

const KIND_COLORS: Record<string, string> = {
  USER: '#22d3ee',
  DEVICE: '#a78bfa',
  IP: '#f59e0b',
  ACCOUNT: '#34d399',
  MERCHANT: '#fb7185',
};

function graphLayout(graph: FraudGraph) {
  const nodes: NodeDatum[] = graph.nodes.map((n) => ({ ...n }));
  const links: LinkDatum[] = graph.edges.map((e) => ({ ...e }));

  const simulation = forceSimulation(nodes)
    .force('link', forceLink<NodeDatum, LinkDatum>(links).id((d) => d.id).distance((d) => 65 + (1 - d.strength) * 35))
    .force('charge', forceManyBody().strength(-250))
    .force('center', forceCenter(220, 160))
    .stop();

  for (let i = 0; i < 70; i += 1) simulation.tick();

  return { nodes, links };
}

export function GraphViewer({ graph }: { graph: FraudGraph | null }) {
  const layout = useMemo(() => (graph ? graphLayout(graph) : null), [graph]);

  if (!graph || !layout) {
    return (
      <GlassPanel className="p-5">
        <SectionHeader title="Neo4j relationship graph" subtitle="User <-> Device <-> IP <-> Account <-> Merchant" />
        <p className="mt-4 text-sm text-slate-400">Select a transaction to render connected-entity intelligence.</p>
      </GlassPanel>
    );
  }

  return (
    <GlassPanel className="p-5">
      <SectionHeader
        title="Neo4j relationship graph"
        subtitle={`Interactive fraud-ring context (${graph.suspicious_clusters} suspicious clusters detected)`}
      />
      <svg viewBox="0 0 440 320" className="mt-4 h-[22rem] w-full rounded-2xl border border-white/10 bg-slate-950/50">
        {layout.links.map((link, idx) => {
          const source = link.source as NodeDatum;
          const target = link.target as NodeDatum;
          return (
            <g key={`link-${idx}`}>
              <line
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="rgba(148,163,184,0.45)"
                strokeWidth={1 + link.strength * 1.8}
              />
              <text
                x={((source.x ?? 0) + (target.x ?? 0)) / 2}
                y={((source.y ?? 0) + (target.y ?? 0)) / 2}
                className="fill-slate-500 text-[9px]"
                textAnchor="middle"
              >
                {link.relation}
              </text>
            </g>
          );
        })}

        {layout.nodes.map((node) => {
          const color = KIND_COLORS[node.kind] ?? '#94a3b8';
          return (
            <g key={node.id}>
              <circle cx={node.x} cy={node.y} r={11 + node.risk * 10} fill={`${color}33`} />
              <circle cx={node.x} cy={node.y} r={6 + node.risk * 5} fill={color} />
              <text x={node.x} y={(node.y ?? 0) - 15} textAnchor="middle" className="fill-white text-[10px] font-medium">
                {node.kind}
              </text>
              <text x={node.x} y={(node.y ?? 0) + 20} textAnchor="middle" className="fill-slate-300 text-[9px] font-mono">
                {node.label.slice(0, 12)}
              </text>
            </g>
          );
        })}
      </svg>
    </GlassPanel>
  );
}
