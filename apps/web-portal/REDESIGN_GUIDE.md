# Frontend Redesign Guide

## Scope and Constraints
- Backend APIs, routes, and data contracts are unchanged.
- Existing route map is preserved:
  - /login
  - /dashboard
  - /live-feed
  - /review-queue
  - /review-queue/[id]
  - /analytics
  - /audit
  - /users

## Design Direction
- Theme: dark-first decision cockpit.
- Style: glassmorphism panels, soft glow edges, high-signal typography.
- Visual base:
  - Background: #0B0F1A equivalent layered gradients.
  - Risk semantics:
    - low: emerald tones
    - medium: amber tones
    - high: rose/red tones

## New Shared UI Architecture

### Core shared files
- app/globals.css
  - dark tokens, glass panel utility class, shimmer and float keyframes.
- components/cockpit.tsx
  - reusable cockpit primitives:
    - PageBackdrop
    - GlassPanel
    - SectionHeader
    - DecisionBadge
    - RoleBadge
    - HealthPulse
    - AnimatedCounter
    - MetricCard
    - RiskGauge
    - SystemHealth
    - StreamTicker
    - FeatureBar / FeatureList
    - SLAChip
    - PermissionMatrix
    - TimelineCard
    - RoleSummary
    - StatusPill
- lib/ui-store.ts
  - Zustand state for:
    - live feed pause/speed
    - dashboard widget ordering

## Route-by-Route Redesign

### Login (/login)
- Animated cockpit-style hero with gradient and particle-like ambient movement.
- Glassmorphic sign-in card.
- Smooth focus transitions for inputs.
- Role-preview demo account chips.

### Dashboard (/dashboard)
- Live cockpit header with role context.
- Animated KPI counters and sparkline-capable metric cards.
- Risk gauge (radial animated).
- Real-time ticker panel.
- Drag-and-drop widget surface.
- System health pulse indicator.
- Role-adaptive sections:
  - ADMIN: control + permissions focus.
  - ANALYST: investigation cards.
  - OPS_MANAGER: queue and throughput emphasis.
  - BANK_PARTNER: simplified trust-first summary.

### Live Feed (/live-feed)
- Streaming timeline cards with animated entry.
- Risk-glow card tones by fraud probability.
- Expandable decision card details with feature proxy bars.
- Controls:
  - pause/resume
  - replay
  - speed (1x, 2x, 5x)

### Review Queue (/review-queue)
- Kanban-style board columns:
  - Open
  - In Review
  - Escalated
  - Closed
- Drag-assisted status movement.
- Selection + bulk operations.
- SLA chip countdown visualization on cards.

### Case Detail (/review-queue/[id])
- Timeline-style decision journey.
- Evidence panel and expanded explanation blocks.
- Analyst resolution controls preserved (assign, verdict, notes, resolve).

### Analytics (/analytics)
- Animated trend displays and drift panel.
- Cluster visualization block.
- Existing A/B output rendered in cockpit table style.

### Audit Trail (/audit)
- Timeline-based expandable decision cards.
- Before/after style evidence grouping.
- Visual trace narrative from ingestion to persistence.

### User Management (/users)
- Role badges and active-state glow.
- Permission matrix.
- Glassmorphic cards for users and API keys.

## Animation System
- Page-level enters via Framer Motion.
- Micro-interactions on buttons and cards.
- Stream card transitions for live feed.
- Skeleton shimmer loaders (no blank loading states).

## Operational Notes
- Frontend dependencies added:
  - framer-motion
  - zustand
- Build optimization support:
  - .dockerignore added to prevent large Docker build contexts.

## Compatibility
- Existing REST and SSE usage remains in lib/api.ts.
- No API payload shape changes were introduced.
