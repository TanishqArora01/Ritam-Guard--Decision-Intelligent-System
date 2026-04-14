'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  ArrowLeftRight,
  FolderOpen,
  BrainCog,
  ShieldCheck,
} from 'lucide-react'
import clsx from 'clsx'
import { useTransactionStore } from '@/store/transactionStore'

const NAV_ITEMS = [
  { label: 'Dashboard', href: '/', icon: LayoutDashboard },
  { label: 'Transactions', href: '/transactions', icon: ArrowLeftRight },
  { label: 'Cases', href: '/cases', icon: FolderOpen },
  { label: 'Models', href: '/models', icon: BrainCog },
]

export default function Sidebar() {
  const pathname = usePathname()
  const isConnected = useTransactionStore((s) => s.isConnected)

  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-full">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-brand-500" />
          <span className="text-lg font-bold text-white tracking-tight">RitamGuard</span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">Decision Intelligence</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                active
                  ? 'bg-brand-500/20 text-brand-400 font-medium'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* System status */}
      <div className="px-5 py-4 border-t border-gray-800">
        <div className="flex items-center gap-2 text-xs">
          <span
            className={clsx(
              'h-2 w-2 rounded-full',
              isConnected ? 'bg-green-400 animate-pulse' : 'bg-gray-500'
            )}
          />
          <span className={isConnected ? 'text-green-400' : 'text-gray-500'}>
            {isConnected ? 'Stream connected' : 'Stream offline'}
          </span>
        </div>
      </div>
    </aside>
  )
}
