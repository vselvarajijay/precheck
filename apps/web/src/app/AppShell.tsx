import { NavLink, Outlet } from 'react-router'
import { useEscalations } from '@/features/lab/api'
import { cn } from '@/shared/lib/utils'
import { HealthBadge } from './HealthBadge'

export const NAV_ITEMS = [
  { to: '/rules', label: 'Rules' },
  { to: '/playground', label: 'Playground' },
  { to: '/tests', label: 'Tests' },
  { to: '/lab', label: 'Agent Lab' },
  { to: '/settings', label: 'Settings' },
] as const

export function AppShell() {
  const pending = useEscalations('pending').data?.length ?? 0
  return (
    <div className="flex min-h-svh bg-background text-foreground">
      <aside className="w-52 shrink-0 border-r bg-sidebar p-3">
        <div className="px-2 py-3 text-sm font-semibold tracking-tight">precheck</div>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-2 py-1.5 text-sm hover:bg-sidebar-accent',
                  isActive && 'bg-sidebar-accent font-medium',
                )
              }
            >
              {item.label}
              {item.to === '/lab' && pending > 0 && (
                <>
                  <span
                    className="ml-2 rounded-full bg-amber-100 px-1.5 text-[11px] font-medium text-amber-900"
                    aria-hidden
                    data-testid="escalation-badge"
                  >
                    {pending}
                  </span>
                  <span className="sr-only"> ({pending} pending escalations)</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-end border-b px-4">
          <HealthBadge />
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
