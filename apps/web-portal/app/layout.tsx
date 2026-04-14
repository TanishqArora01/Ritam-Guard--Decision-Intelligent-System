'use client';
import './globals.css';
import React, { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname, useRouter } from 'next/navigation';
import {
  Activity, BarChart2, FileSearch, Home,
  LogOut, Menu, Users, X, AlertTriangle, Sparkles, Settings, Layers3,
} from 'lucide-react';
import { clearTokens } from '../lib/api';
import { AuthProvider, useAuth } from '../lib/auth-context';
import type { Role } from '../lib/types';
import { HealthPulse, RoleBadge, StatusPill } from '../components/cockpit';

// ---------------------------------------------------------------------------
// Nav items — role-gated
// ---------------------------------------------------------------------------
const NAV: { label: string; href: string; icon: React.FC<any>; roles: Role[] }[] = [
  { label: 'Dashboard',    href: '/dashboard',    icon: Home,       roles: ['ANALYST','OPS_MANAGER','ADMIN','BANK_PARTNER'] },
  { label: 'Transactions', href: '/transactions', icon: Activity,   roles: ['ANALYST','OPS_MANAGER','ADMIN','BANK_PARTNER'] },
  { label: 'Cases',        href: '/cases',        icon: AlertTriangle, roles: ['ANALYST','OPS_MANAGER','ADMIN'] },
  { label: 'Models',       href: '/models',       icon: Sparkles, roles: ['ANALYST','OPS_MANAGER','ADMIN'] },
  { label: 'Analytics',    href: '/analytics',    icon: BarChart2,  roles: ['OPS_MANAGER','ADMIN','BANK_PARTNER'] },
  { label: 'Audit Trail',  href: '/audit',        icon: FileSearch, roles: ['ANALYST','OPS_MANAGER','ADMIN','BANK_PARTNER'] },
  { label: 'Users',        href: '/users',        icon: Users,      roles: ['ADMIN'] },
];

const ROLE_COLORS: Record<Role, string> = {
  ADMIN:        'bg-red-100 text-red-700',
  OPS_MANAGER:  'bg-purple-100 text-purple-700',
  ANALYST:      'bg-blue-100 text-blue-700',
  BANK_PARTNER: 'bg-green-100 text-green-700',
};

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, setUser } = useAuth();

  const logout = () => {
    clearTokens();
    setUser(null);
    router.push('/login');
  };

  const filteredNav = NAV.filter((item) => !user || item.roles.includes(user.role as Role));

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-20 bg-black/50 backdrop-blur-sm lg:hidden" onClick={onClose} />
      )}
      <aside className={`fixed top-0 left-0 z-30 h-full w-72 border-r border-white/10 text-white flex flex-col transform transition-transform duration-200 glass-panel ${open ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 lg:static lg:z-auto`}>
        <div className="px-5 py-5 border-b border-white/10">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400/20 to-violet-500/20 ring-1 ring-white/10">
                <Image src="/ritam-guard-logo.png" alt="Ritam Guard" width={44} height={44} className="h-10 w-10 rounded-xl object-cover" priority />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Ritam Guard</p>
                <span className="font-semibold text-lg tracking-tight text-white">Ritam Guard</span>
              </div>
            </div>
            <button onClick={onClose} className="lg:hidden text-slate-400 hover:text-white">
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
            <Sparkles className="h-4 w-4 text-cyan-300" /> Real-time intelligence cockpit
          </div>
        </div>

        <div className="px-4 py-4 space-y-3">
          <div className="flex items-center justify-between rounded-2xl bg-white/5 px-3 py-2 ring-1 ring-white/10">
            <div>
              <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Stream status</p>
              <p className="text-sm text-white">Live and adaptive</p>
            </div>
            <HealthPulse status="healthy" />
          </div>
          {user && (
            <div className="flex items-center justify-between rounded-2xl bg-white/5 px-3 py-2 ring-1 ring-white/10">
              <div>
                <p className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Signed in</p>
                <p className="text-sm font-medium text-white truncate">{user.username}</p>
              </div>
              <RoleBadge role={user.role as Role} />
            </div>
          )}
        </div>

        <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto scrollbar-thin">
          {filteredNav.map(({ label, href, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link key={href} href={href} onClick={onClose} className={`group flex items-center gap-3 px-3 py-3 rounded-2xl text-sm font-medium transition-all duration-200 ${active ? 'bg-white/10 text-white ring-1 ring-cyan-400/25 shadow-[0_0_24px_rgba(34,211,238,0.08)]' : 'text-slate-300 hover:bg-white/5 hover:text-white'}`}>
                <Icon className="w-4 h-4 text-slate-300 group-hover:text-cyan-300" />
                <span className="flex-1">{label}</span>
                {active && <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.8)]" />}
              </Link>
            );
          })}
        </nav>

        {user && (
          <div className="border-t border-white/10 p-4 space-y-3">
            <div className="flex items-center gap-3 rounded-2xl bg-white/5 px-3 py-3 ring-1 ring-white/10">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400/20 to-violet-500/20 text-sm font-semibold uppercase ring-1 ring-white/10">
                {user.username[0]}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">{user.username}</p>
                <div className="mt-1 flex items-center gap-2">
                  <RoleBadge role={user.role as Role} />
                </div>
              </div>
            </div>
            <button onClick={logout} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-rose-500/10 px-3 py-3 text-sm font-medium text-rose-200 ring-1 ring-rose-400/20 transition hover:bg-rose-500/15">
              <LogOut className="w-4 h-4" /> Sign out
            </button>
          </div>
        )}
      </aside>
    </>
  );
}

  function TopBar({ onOpen }: { onOpen: () => void }) {
    const { user } = useAuth();
    return (
      <header className="sticky top-0 z-10 border-b border-white/10 bg-slate-950/70 backdrop-blur-xl">
        <div className="flex items-center justify-between gap-4 px-4 py-3 lg:px-6">
          <div className="flex items-center gap-3">
            <button onClick={onOpen} className="rounded-2xl border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:text-white lg:hidden">
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">Ritam Guard Decision Intelligence System</p>
              <h1 className="text-sm font-semibold text-white">AI decision cockpit</h1>
            </div>
          </div>
          <div className="hidden items-center gap-3 md:flex">
            <StatusPill label="Streaming" tone="emerald" />
            <StatusPill label="SSE active" tone="cyan" />
            {user && <RoleBadge role={user.role as Role} />}
            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300">
              <Layers3 className="h-3.5 w-3.5 text-cyan-300" /> Live system view
            </div>
            <button className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:text-white">
              <Settings className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>
    );
  }

// ---------------------------------------------------------------------------
// Root layout
// ---------------------------------------------------------------------------
export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [sideOpen, setSideOpen] = useState(false);
  const pathname = usePathname();
  const isLogin  = pathname === '/login';

  if (isLogin) {
    return (
      <html lang="en">
        <body className="bg-slate-950 text-slate-100 antialiased">
          <AuthProvider>
            {children}
          </AuthProvider>
        </body>
      </html>
    );
  }

  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 antialiased">
        <AuthProvider>
          <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100">
            <Sidebar open={sideOpen} onClose={() => setSideOpen(false)} />
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
              <TopBar onOpen={() => setSideOpen(true)} />
              <main className="relative flex-1 overflow-y-auto scrollbar-thin">
                {children}
              </main>
            </div>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
