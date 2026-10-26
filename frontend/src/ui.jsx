// Small shared pieces: icons, toasts, drawer, avatars, status labels, date helpers.

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

// ---------- icons (inline SVG, 20px grid, stroke follows currentColor) ----------

const PATHS = {
  overview: 'M3 10.5 10 4l7 6.5M5 9v7h4v-4h2v4h4V9',
  board: 'M3 4h4v12H3zM8.5 4h4v8h-4zM14 4h3v5h-3z',
  docs: 'M5 2.5h6l4 4V17a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 5 17zM11 2.5V7h4M7.5 11h5M7.5 14h5',
  planner: 'M4 4h5v5H4zM11 11h5v5h-5zM9 6.5h2.5a2 2 0 0 1 2 2V11',
  team: 'M7 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 17c0-3 2.2-5 5-5s5 2 5 5M13.5 9a2.5 2.5 0 1 0 0-5M14 12c2.4.3 4 2.1 4 5',
  plus: 'M10 4v12M4 10h12',
  close: 'M5 5l10 10M15 5 5 15',
  upload: 'M10 13V3M6 7l4-4 4 4M3.5 13v3.5h13V13',
  send: 'M3 10h11M10 5l5 5-5 5',
  alert: 'M10 3 2 17h16zM10 8v4M10 14.5v.5',
  clock: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM10 6v4l3 2',
  link: 'M8.5 11.5l3-3M7 9.5 5.5 11a2.5 2.5 0 0 0 3.5 3.5l1.5-1.5M13 10.5l1.5-1.5A2.5 2.5 0 0 0 11 5.5L9.5 7',
  check: 'M4 10.5 8 14.5 16 5.5',
  trash: 'M4 6h12M8 6V4h4v2M6 6l1 11h6l1-11',
  sun: 'M10 13.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM10 1.5v2M10 16.5v2M1.5 10h2M16.5 10h2M4 4l1.4 1.4M14.6 14.6 16 16M4 16l1.4-1.4M14.6 5.4 16 4',
  moon: 'M16 12.5A7 7 0 0 1 7.5 4a7 7 0 1 0 8.5 8.5z',
  logout: 'M8 4H4v12h4M12 6l4 4-4 4M16 10H8',
  spark: 'M10 2.5 11.6 8.4 17.5 10 11.6 11.6 10 17.5 8.4 11.6 2.5 10 8.4 8.4z',
  file: 'M5 2.5h6l4 4V17a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 5 17zM11 2.5V7h4',
  chevron: 'M8 5l5 5-5 5',
}

export function Icon({ name, size = 18, className = '' }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 20 20" fill="none"
         stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  )
}

// ---------- toasts ----------

const ToastContext = createContext(() => {})

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = useCallback((text, kind = 'ok') => {
    const id = Math.random().toString(36).slice(2)
    setToasts((list) => [...list, { id, text, kind }].slice(-3)) // keep the three newest
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), kind === 'error' ? 6000 : 3200)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <Icon name={t.kind === 'error' ? 'alert' : 'check'} size={16} />
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)

// ---------- drawer ----------

export function Drawer({ open, title, onClose, children }) {
  const panel = useRef(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    panel.current?.querySelector('input, textarea, select, button')?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="drawer-layer">
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title} ref={panel}>
        <header className="drawer-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  )
}

// ---------- people and statuses ----------

export function nameFromEmail(email = '') {
  const local = email.split('@')[0].replace(/-[0-9a-f]{8}$/, '') // demo users carry a random tag
  return local.split(/[._-]/).filter(Boolean).map((p) => p[0].toUpperCase() + p.slice(1)).join(' ') || email
}

export function Avatar({ email, size = 26 }) {
  const name = nameFromEmail(email)
  const initials = name.split(' ').map((p) => p[0]).join('').slice(0, 2)
  let hash = 0
  for (const ch of email) hash = (hash * 31 + ch.charCodeAt(0)) % 360
  return (
    <span className="avatar" style={{ width: size, height: size, '--hue': hash }} title={email}>
      {initials}
    </span>
  )
}

export const STATUSES = [
  { key: 'todo', label: 'To do' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'blocked', label: 'Blocked' },
  { key: 'done', label: 'Done' },
]

export const statusLabel = (key) => STATUSES.find((s) => s.key === key)?.label ?? key

export function StatusTag({ status }) {
  return <span className={`status-tag s-${status}`}><i />{statusLabel(status)}</span>
}

// ---------- dates ----------

export function todayISO() {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

export function dueInfo(due, status) {
  if (!due) return null
  const days = Math.round((new Date(due) - new Date(todayISO())) / 86400000)
  const label = new Date(due).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  if (status === 'done') return { label, tone: 'quiet' }
  if (days < 0) return { label: `${label}, ${-days}d late`, tone: 'late' }
  if (days === 0) return { label: 'Due today', tone: 'soon' }
  if (days <= 2) return { label: `${label}, in ${days}d`, tone: 'soon' }
  return { label, tone: 'quiet' }
}

export function timeAgo(iso) {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {children && <p className="empty-text">{children}</p>}
      {action}
    </div>
  )
}
