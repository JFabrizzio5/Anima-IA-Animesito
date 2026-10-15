import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'

import BaseIcon from '@/components/BaseIcon.jsx'
import EngineStatus from '@/components/EngineStatus.jsx'
import JobDock from '@/components/JobDock.jsx'
import ThemeToggle from '@/components/ThemeToggle.jsx'
import menu from '@/menuAside.js'
import { connectJobEvents } from '@/stores/jobs.store.js'

const LINK = 'mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors'
const INACTIVE = 'text-ink-soft hover:bg-elevated hover:text-ink'
const ACTIVE = 'bg-brand-50 font-medium text-brand-700 dark:bg-brand-900/25 dark:text-brand-300'

export default function AppLayout({ children }) {
  const appName = import.meta.env.VITE_APP_NAME || 'Animesito'
  const [open, setOpen] = useState(false)

  useEffect(() => {
    connectJobEvents()
  }, [])

  // Same scroll lock and breakpoint handling as the JFast template's layout.
  useEffect(() => {
    if (!open) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open])

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 768px)')
    const closeOnDesktop = (event) => event.matches && setOpen(false)
    desktop.addEventListener('change', closeOnDesktop)
    return () => desktop.removeEventListener('change', closeOnDesktop)
  }, [])

  return (
    <div className="flex min-h-full bg-surface text-ink">
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-56 shrink-0 flex-col border-r border-line bg-panel transition-transform duration-200 md:static md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center gap-2.5 border-b border-line px-5">
          <span className="size-2 rounded-full bg-brand-500" aria-hidden="true" />
          <span className="truncate font-semibold tracking-tight">{appName}</span>
        </div>
        <nav className="flex-1 overflow-y-auto p-3">
          {menu.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={() => setOpen(false)}
              className={({ isActive }) => `${LINK} ${isActive ? ACTIVE : INACTIVE}`}
            >
              <BaseIcon path={item.icon} size="sm" className="shrink-0" />
              <span className="truncate">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {open ? (
        <div
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-panel/80 px-4 backdrop-blur md:px-6">
          <button
            type="button"
            className="rounded-lg p-2 text-ink-soft hover:bg-elevated hover:text-ink md:hidden"
            aria-expanded={open}
            aria-label="Abrir navegación"
            onClick={() => setOpen((value) => !value)}
          >
            <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="font-semibold md:hidden">{appName}</span>
          <div className="flex-1" />
          <EngineStatus />
          <ThemeToggle />
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      <JobDock />
    </div>
  )
}
