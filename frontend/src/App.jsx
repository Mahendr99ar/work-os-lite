import { useCallback, useEffect, useState } from 'react'
import { api, tokenStore } from './api.js'
import { Avatar, Icon, ToastProvider, nameFromEmail } from './ui.jsx'
import Login from './pages/Login.jsx'
import Overview from './pages/Overview.jsx'
import Board from './pages/Board.jsx'
import Docs from './pages/Docs.jsx'
import Planner from './pages/Planner.jsx'
import Team from './pages/Team.jsx'

const PAGES = [
  { key: 'overview', label: 'Overview', icon: 'overview', Component: Overview },
  { key: 'board', label: 'Board', icon: 'board', Component: Board },
  { key: 'docs', label: 'Ask docs', icon: 'docs', Component: Docs },
  { key: 'planner', label: 'AI planner', icon: 'planner', Component: Planner },
  { key: 'team', label: 'Team', icon: 'team', Component: Team },
]

// The page lives in the URL hash (#/board), so refresh and the back button work without a router library.
function currentPage() {
  const key = window.location.hash.replace(/^#\/?/, '').split('?')[0]
  return PAGES.some((p) => p.key === key) ? key : 'overview'
}

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme') || 'auto' } catch { return 'auto' }
  })
  useEffect(() => {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    try { localStorage.setItem('theme', theme) } catch { /* ignore */ }
  }, [theme])
  const isDark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  return [isDark, () => setTheme(isDark ? 'light' : 'dark')]
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  )
}

function Shell() {
  const [user, setUser] = useState(null)
  const [meta, setMeta] = useState(null)
  const [page, setPage] = useState(currentPage)
  const [checking, setChecking] = useState(Boolean(tokenStore.get()))
  const [isDark, toggleTheme] = useTheme()

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null))
    const onHash = () => setPage(currentPage())
    const onLogout = () => setUser(null)
    window.addEventListener('hashchange', onHash)
    window.addEventListener('workos:logout', onLogout)
    if (tokenStore.get()) {
      api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setChecking(false))
    }
    return () => {
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener('workos:logout', onLogout)
    }
  }, [])

  const go = useCallback((key) => { window.location.hash = `/${key}` }, [])

  function logout() {
    tokenStore.clear()
    setUser(null)
  }

  if (checking) return <div className="boot" aria-busy="true" />
  if (!user) return <Login meta={meta} onLogin={(u) => { setUser(u); go('overview') }} />

  const Current = PAGES.find((p) => p.key === page).Component

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="workspace">
          <span className="logo-mark" aria-hidden="true" />
          <div>
            <div className="workspace-name">{user.team_name || 'Workspace'}</div>
            <div className="workspace-sub">Work OS Lite</div>
          </div>
        </div>
        <nav className="nav" aria-label="Main">
          {PAGES.map((p) => (
            <a key={p.key} href={`#/${p.key}`} className={page === p.key ? 'nav-item active' : 'nav-item'}
               aria-current={page === p.key ? 'page' : undefined}>
              <Icon name={p.icon} />
              <span>{p.label}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="me">
            <Avatar email={user.email} size={30} />
            <div className="me-text">
              <div className="me-name">{nameFromEmail(user.email)}</div>
              <div className="me-role">{user.role === 'admin' ? 'Admin' : 'Member'}</div>
            </div>
          </div>
          <div className="foot-actions">
            <button className="icon-btn" onClick={toggleTheme} aria-label={isDark ? 'Use light theme' : 'Use dark theme'}>
              <Icon name={isDark ? 'sun' : 'moon'} />
            </button>
            <button className="icon-btn" onClick={logout} aria-label="Log out"><Icon name="logout" /></button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="mobile-top">
          <span className="logo-mark" aria-hidden="true" />
          <span className="workspace-name">{user.team_name || 'Workspace'}</span>
          <span className="spacer" />
          <button className="icon-btn" onClick={toggleTheme} aria-label={isDark ? 'Use light theme' : 'Use dark theme'}>
            <Icon name={isDark ? 'sun' : 'moon'} />
          </button>
          <button className="icon-btn" onClick={logout} aria-label="Log out"><Icon name="logout" /></button>
        </header>
        {meta && !meta.llm_configured && (
          <div className="notice">
            AI answers and plans are off because the server has no LLM_API_KEY. Everything else works.
          </div>
        )}
        <main className="content" key={page}>
          <Current user={user} meta={meta} go={go} />
        </main>
      </div>
    </div>
  )
}
