import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, Icon, timeAgo, useToast } from '../ui.jsx'
import { PageSkeleton } from './Overview.jsx'

const EXAMPLE = 'We launch the mobile app on 1 Dec. We need email login, payments through Razorpay and a landing page. ' +
  'Payments can only start once login works. Marketing wants a demo video a week before launch.'

export default function Planner({ user, meta, go }) {
  const toast = useToast()
  const [projects, setProjects] = useState(null)
  const [plans, setPlans] = useState([])
  const [projectId, setProjectId] = useState('')
  const [brief, setBrief] = useState('')
  const [busy, setBusy] = useState(false)
  const [reviewing, setReviewing] = useState(null)
  const isAdmin = user.role === 'admin'

  useEffect(() => {
    Promise.all([api.projects(), api.plans()]).then(([list, existing]) => {
      setProjects(list)
      setPlans(existing)
      if (list.length) setProjectId(String(list[0].id))
    }).catch((e) => toast(e.message, 'error'))
  }, [toast])

  async function generate(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const plan = await api.createPlan(Number(projectId), brief)
      setPlans((list) => [plan, ...list])
      setBrief('')
      toast(`Drafted ${plan.plan_json.tasks.length} tasks. They are not on the board until approved.`)
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  async function review(plan, approve) {
    if (reviewing) return
    setReviewing(plan.id)
    try {
      if (approve) {
        const created = await api.approvePlan(plan.id)
        toast(`Approved. ${created.length} tasks added to the board.`)
      } else {
        await api.rejectPlan(plan.id)
        toast('Rejected. Nothing was added to the board.')
      }
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      // Always re-read the plans. If someone else reviewed this plan first (409),
      // the page now shows the real status instead of a stale "Draft".
      try { setPlans(await api.plans()) } catch { /* keep what we have */ }
      setReviewing(null)
    }
  }

  if (!projects) return <PageSkeleton />

  const projectName = (id) => projects.find((p) => p.id === id)?.name ?? 'Deleted project'
  const pending = plans.filter((p) => p.status === 'pending')
  const reviewed = plans.filter((p) => p.status !== 'pending')

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>AI planner</h1>
          <p className="lede">Paste a messy brief. The AI drafts tasks and their order. Drafts stay off the board until an admin approves them.</p>
        </div>
      </header>

      {projects.length === 0 ? (
        <EmptyState title="Plans belong to a project." action={<button className="btn btn-primary" onClick={() => go('board')}>Create a project</button>}>
          Create one on the board first.
        </EmptyState>
      ) : (
        <form className="brief" onSubmit={generate}>
          <div className="brief-top">
            <label className="field field-inline">Project
              <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <button type="button" className="btn btn-quiet" onClick={() => setBrief(EXAMPLE)}>Use an example brief</button>
          </div>
          <textarea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)} required minLength={20} maxLength={8000}
                    placeholder="Goals, deadlines, what has to happen before what. Plain sentences are fine." aria-label="Project brief" />
          <div className="brief-bottom">
            <span className="hint">{brief.length < 20 ? `${20 - brief.length} more characters needed` : `${brief.length} characters`}</span>
            <button className="btn btn-draft" disabled={busy || brief.length < 20 || meta?.llm_configured === false}>
              <Icon name="spark" size={16} />{busy ? 'Drafting tasks' : 'Draft a plan'}
            </button>
          </div>
        </form>
      )}

      {pending.length > 0 && (
        <section className="section">
          <h2 className="section-title">Waiting for review</h2>
          {pending.map((plan) => (
            <PlanCard key={plan.id} plan={plan} projectName={projectName(plan.project_id)}>
              {isAdmin ? (
                <div className="plan-actions">
                  <button className="btn btn-primary" disabled={reviewing === plan.id} onClick={() => review(plan, true)}>
                    <Icon name="check" size={16} />Approve and add {plan.plan_json.tasks.length} tasks
                  </button>
                  <button className="btn" disabled={reviewing === plan.id} onClick={() => review(plan, false)}>Reject</button>
                </div>
              ) : <p className="hint">Only an admin can approve this plan.</p>}
            </PlanCard>
          ))}
        </section>
      )}

      {reviewed.length > 0 && (
        <section className="section">
          <h2 className="section-title">Reviewed</h2>
          {reviewed.map((plan) => <PlanCard key={plan.id} plan={plan} projectName={projectName(plan.project_id)} compact />)}
        </section>
      )}

      {plans.length === 0 && projects.length > 0 && (
        <EmptyState title="No plans yet.">Drafted plans appear here, ready for an admin to approve or reject.</EmptyState>
      )}
    </div>
  )
}

function PlanCard({ plan, projectName, compact = false, children }) {
  const [open, setOpen] = useState(!compact)
  const tasks = plan.plan_json.tasks
  const state = plan.status
  return (
    <article className={`plan plan-${state}`}>
      <header className="plan-head">
        <div>
          <div className="plan-title">{projectName}</div>
          <div className="plan-meta">{tasks.length} tasks, drafted {timeAgo(plan.created_at)}</div>
        </div>
        <span className={`plan-state ps-${state}`}>
          {state === 'pending' ? 'Draft' : state === 'approved' ? 'Approved' : 'Rejected'}
        </span>
      </header>

      {open && (
        <>
          <blockquote className="plan-brief">{plan.brief}</blockquote>
          {/* The list order matters: depends_on refers to these numbers. */}
          <ol className="plan-tasks">
            {tasks.map((t, i) => (
              <li key={i} className="plan-task">
                <span className="plan-num">{i + 1}</span>
                <div className="plan-body">
                  <div className="plan-task-title">{t.title}</div>
                  {t.description && <div className="plan-task-desc">{t.description}</div>}
                  <div className="plan-task-meta">
                    {t.depends_on ? <span><Icon name="link" size={13} />After {t.depends_on}. {tasks[t.depends_on - 1]?.title}</span> : <span>Can start now</span>}
                    {t.estimate_days && <span>About {t.estimate_days} {t.estimate_days === 1 ? 'day' : 'days'}</span>}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          {children}
        </>
      )}
      {compact && (
        <button className="btn btn-quiet plan-toggle" onClick={() => setOpen(!open)}>{open ? 'Hide tasks' : 'Show tasks'}</button>
      )}
    </article>
  )
}
