'use client';
import React from 'react';
import type { Action } from '../lib/types';

// ---------------------------------------------------------------------------
// DecisionBadge
// ---------------------------------------------------------------------------
const ACTION_STYLES: Record<string, string> = {
  APPROVE:       'bg-green-100  text-green-800  border-green-200',
  BLOCK:         'bg-red-100    text-red-800    border-red-200',
  STEP_UP_AUTH:  'bg-amber-100  text-amber-800  border-amber-200',
  MANUAL_REVIEW: 'bg-purple-100 text-purple-800 border-purple-200',
};
const ACTION_LABELS: Record<string, string> = {
  APPROVE: 'Approve', BLOCK: 'Block',
  STEP_UP_AUTH: 'Step-Up', MANUAL_REVIEW: 'Review',
};

export function DecisionBadge({ action, size = 'sm' }: { action: string; size?: 'xs' | 'sm' | 'md' }) {
  const style  = ACTION_STYLES[action] ?? 'bg-gray-100 text-gray-700 border-gray-200';
  const label  = ACTION_LABELS[action] ?? action;
  const padding = size === 'xs' ? 'px-1.5 py-0.5 text-xs' :
                  size === 'md' ? 'px-3 py-1 text-sm' :
                  'px-2 py-0.5 text-xs';
  return (
    <span className={`inline-flex items-center font-semibold rounded-full border ${style} ${padding}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// FraudScoreBar
// ---------------------------------------------------------------------------
export function FraudScoreBar({ score, showLabel = true }: { score: number; showLabel?: boolean }) {
  const pct   = Math.round(score * 100);
  const color = score >= 0.7 ? 'bg-red-500' :
                score >= 0.4 ? 'bg-amber-500' :
                               'bg-green-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-1.5 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      {showLabel && (
        <span className={`text-xs font-mono font-semibold w-10 text-right
          ${score >= 0.7 ? 'text-red-600' : score >= 0.4 ? 'text-amber-600' : 'text-green-600'}`}>
          {pct}%
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// KpiCard
// ---------------------------------------------------------------------------
export function KpiCard({
  title, value, sub, icon: Icon, color = 'blue',
}: {
  title: string; value: string | number; sub?: string;
  icon?: React.FC<any>; color?: string;
}) {
  const colors: Record<string, string> = {
    blue:   'bg-blue-50   text-blue-600',
    green:  'bg-green-50  text-green-600',
    red:    'bg-red-50    text-red-600',
    amber:  'bg-amber-50  text-amber-600',
    purple: 'bg-purple-50 text-purple-600',
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4">
      {Icon && (
        <div className={`p-2.5 rounded-lg ${colors[color] ?? colors.blue}`}>
          <Icon className="w-5 h-5" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
        <p className="text-2xl font-bold text-gray-900 mt-0.5">{value}</p>
        {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------
export function Spinner({ className = 'w-6 h-6' }: { className?: string }) {
  return (
    <svg className={`animate-spin text-blue-500 ${className}`} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// CasePriorityBadge
// ---------------------------------------------------------------------------
const PRIORITY_STYLES: Record<number, string> = {
  1: 'bg-red-100 text-red-700 border-red-200',
  2: 'bg-amber-100 text-amber-700 border-amber-200',
  3: 'bg-gray-100 text-gray-600 border-gray-200',
};
const PRIORITY_LABELS: Record<number, string> = { 1: 'High', 2: 'Medium', 3: 'Low' };

export function PriorityBadge({ priority }: { priority: number }) {
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border
      ${PRIORITY_STYLES[priority] ?? PRIORITY_STYLES[3]}`}>
      {PRIORITY_LABELS[priority] ?? 'Unknown'}
    </span>
  );
}

// ---------------------------------------------------------------------------
// StatusBadge (case status)
// ---------------------------------------------------------------------------
const STATUS_STYLES: Record<string, string> = {
  OPEN:       'bg-blue-100  text-blue-700',
  IN_REVIEW:  'bg-amber-100 text-amber-700',
  RESOLVED:   'bg-green-100 text-green-700',
  ESCALATED:  'bg-red-100   text-red-700',
};
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full
      ${STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------
export function EmptyState({ title, description, icon: Icon }: {
  title: string; description?: string; icon?: React.FC<any>;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {Icon && <Icon className="w-10 h-10 text-gray-300 mb-3" />}
      <p className="font-medium text-gray-500">{title}</p>
      {description && <p className="text-sm text-gray-400 mt-1">{description}</p>}
    </div>
  );
}

export * from './cockpit';
export * from './TransactionStream';
export * from './DecisionFlow';
export * from './ExplainabilityPanel';
export * from './GraphViewer';
export * from './MetricsDashboard';
