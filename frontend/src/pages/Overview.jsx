import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, Icon, STATUSES, dueInfo, todayISO, useToast } from '../ui.jsx'

export default function Overview({ user, go }) {
  const toast = useToast()
  const [data, setData] = useState(null)

  useEffect(() => {
    Promise.all([api.projects(), api.allTasks(), api.blocked(), api.plans()])
      .then(([projects, tasks, blocked, plans]) => setData({ projects, tasks, blocked, plans }))
      .catch((e) => toast(e.message, 'error'))
  }, [toast])

  if (!data) return <PageSkeleton />

  const { projects, tasks, blocked, plans } = data
  const projectName = (id) => projects.find((p) => p.id === id)?.name ?? ''
  const today = todayISO()
  const overdue = tasks.filter((t) => t.due_date && t.due_date < today && t.status !== 'done')
  const pending = plans.filter((p) => p.status === 'pending')
  const open = tasks.filter((t) => t.status !== 'done').length

  const attention = [
    ...pending.map((p) => ({
      key: `plan-${p.id}`, kind: 'draft', icon: 'spark',
      title: `AI plan with ${p.plan_json.tasks.length} tasks is waiting for review`,
      detail: projectName(p.project_id),
      action: () => go('planner'), actionLabel: user.role === 'admin' ? 'Review' : 'View',
    })),
    ...blocked.map((b) => ({
      key: `blocked-${b.task.id}`, kind: 'blocked', icon: 'link',
      title: b.task.title, detail: `${projectName(b.task.project_id)}. ${b.reason}`,
      action: () => go('board'), actionLabel: 'Open board',
    })),
    ...overdue.filter((t) => !blocked.some((b) => b.task.id === t.id)).map((t) => ({
      key: `late-${t.id}`, kind: 'late', icon: 'clock',
      title: t.title, detail: `${projectName(t.project_id)}. ${dueInfo(t.due_date, t.status).label}`,
      action: () => go('board'), actionLabel: 'Open board',
    })),
  ]

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Overview</h1>
          <p className="lede">
            {open} open {open === 1 ? 'task' : 'tasks'} across {projects.length} {projects.length === 1 ? 'project' : 'projects'}.
            {attention.length > 0 ? ` ${attention.length} need attention.` : ' Nothing is stuck.'}
          </p>
        </div>
      </header>

      <section className="section">
        <h2 className="section-title">Needs attention</h2>
        {attention.length === 0 ? (
          <EmptyState title="Nothing blocked, late or waiting on review.">
            New blockers and AI plans that need a decision will show up here.
          </EmptyState>
        ) : (
          <ul className="attention">
            {attention.map((item) => (
              <li key={item.key} className={`attention-row k-${item.kind}`}>
                <span className="attention-icon"><Icon name={item.icon} size={16} /></span>
                <div className="attention-text">
                  <div className="attention-title">{item.title}</div>
                  <div className="attention-detail">{item.detail}</div>
                </div>
                <button className="btn btn-quiet" onClick={item.action}>{item.actionLabel}</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section">
        <div className="section-bar">
          <h2 className="section-title">Projects</h2>
          <button className="btn btn-quiet" onClick={() => go('board')}><Icon name="plus" size={16} />New project</button>
        </div>
        {projects.length === 0 ? (
          <EmptyState title="No projects yet." action={<button className="btn btn-primary" onClick={() => go('board')}>Create a project</button>}>
            Start on the board, or paste a brief into the AI planner.
          </EmptyState>
        ) : (
          <div className="projects">
            {projects.map((p) => {
              const own = tasks.filter((t) => t.project_id === p.id)
              const done = own.filter((t) => t.status === 'done').length
              const next = own.filter((t) => t.status !== 'done' && t.due_date).sort((a, b) => a.due_date.localeCompare(b.due_date))[0]
              return (
                <button key={p.id} className="project-row" onClick={() => go(`board?project=${p.id}`)}>
                  <div className="project-main">
                    <div className="project-name">{p.name}</div>
                    {p.description && <div className="project-desc">{p.description}</div>}
                  </div>
                  <div className="project-progress">
                    <div className="bar" role="img" aria-label={`${done} of ${own.length} tasks done`}>
                      {own.length === 0 ? <span className="bar-empty" /> : STATUSES.map((s) => {
                        const n = own.filter((t) => t.status === s.key).length
                        return n ? <span key={s.key} className={`bar-seg s-${s.key}`} style={{ flexGrow: n }} title={`${s.label}: ${n}`} /> : null
                      })}
                    </div>
                    <div className="project-meta">
                      <span>{done} of {own.length} done</span>
                      {next && <span>Next due: {next.title}, {dueInfo(next.due_date, next.status).label}</span>}
                    </div>
                  </div>
                  <Icon name="chevron" className="project-go" />
                </button>
              )
            })}
          </div>
        )}
        <div className="legend">
          {STATUSES.map((s) => <span key={s.key} className={`legend-item s-${s.key}`}><i />{s.label}</span>)}
        </div>
      </section>
    </div>
  )
}

export function PageSkeleton() {
  return (
    <div className="page" aria-busy="true">
      <div className="skeleton sk-title" />
      <div className="skeleton sk-line" />
      <div className="skeleton sk-block" />
    </div>
  )
}
