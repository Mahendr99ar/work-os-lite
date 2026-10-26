import { Fragment, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Avatar, Drawer, EmptyState, Icon, nameFromEmail, timeAgo, useToast } from '../ui.jsx'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'ask', label: 'Questions' },
  { key: 'plan', label: 'Plans' },
]

const ACTION_LABEL = { ask: 'Asked docs', plan_generate: 'Drafted a plan', plan_review: 'Reviewed a plan' }

export default function Team({ user }) {
  const toast = useToast()
  const [members, setMembers] = useState([])
  const [audit, setAudit] = useState(null)
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [adding, setAdding] = useState(false)
  const isAdmin = user.role === 'admin'

  useEffect(() => { load() }, [])

  async function load() {
    try {
      setMembers(await api.members())
      if (isAdmin) setAudit(await api.audit())
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const emailOf = (id) => members.find((m) => m.id === id)?.email ?? `User ${id}`
  const rows = (audit || []).filter((r) => filter === 'all' || r.action.startsWith(filter))

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Team</h1>
          <p className="lede">{members.length} {members.length === 1 ? 'person' : 'people'} in {user.team_name || 'this workspace'}. Admins approve AI plans and see every AI call.</p>
        </div>
        {isAdmin && <div className="head-actions"><button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" size={16} />Add member</button></div>}
      </header>

      <section className="section">
        <h2 className="section-title">People</h2>
        <ul className="people">
          {members.map((m) => (
            <li key={m.id}>
              <Avatar email={m.email} size={34} />
              <div className="person">
                <div className="person-name">{nameFromEmail(m.email)}{m.id === user.id && <span className="you">You</span>}</div>
                <div className="person-mail">{m.email}</div>
              </div>
              <span className={`role role-${m.role}`}>{m.role === 'admin' ? 'Admin' : 'Member'}</span>
            </li>
          ))}
        </ul>
      </section>

      {isAdmin && (
        <section className="section">
          <div className="section-bar">
            <h2 className="section-title">AI audit log</h2>
            <div className="filters" role="tablist">
              {FILTERS.map((f) => (
                <button key={f.key} role="tab" aria-selected={filter === f.key} className={filter === f.key ? 'filter on' : 'filter'}
                        onClick={() => setFilter(f.key)}>{f.label}</button>
              ))}
            </div>
          </div>
          <p className="hint section-hint">Every question, every drafted plan and every approval, newest first. Click a row to see what the model returned.</p>
          {audit === null ? <div className="skeleton sk-block" /> : rows.length === 0 ? (
            <EmptyState title="No AI activity yet.">Ask a question in Ask docs or draft a plan to see it logged here.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="audit">
                <thead>
                  <tr><th>When</th><th>Who</th><th>What</th><th>Input</th><th>Result</th></tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <Fragment key={r.id}>
                      <tr className={expanded === r.id ? 'is-open' : ''} onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                          tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && setExpanded(expanded === r.id ? null : r.id)}>
                        <td className="nowrap">{timeAgo(r.created_at)}</td>
                        <td className="nowrap">{nameFromEmail(emailOf(r.user_id))}</td>
                        <td className="nowrap">{ACTION_LABEL[r.action] ?? r.action}</td>
                        <td className="cell-input">{r.input_summary}</td>
                        <td><span className={`result r-${r.status}`}>{r.status}</span></td>
                      </tr>
                      {expanded === r.id && (
                        <tr className="audit-detail">
                          <td colSpan={5}>
                            {r.action === 'plan_review' ? (
                              <div className="detail-label">A person {r.status} plan {r.plan_id ?? ''}. No model call.</div>
                            ) : (
                              <>
                                <div className="detail-label">Model output</div>
                                <pre>{r.output || 'No model call was made: no document was close enough, so the question was refused before reaching the AI.'}</pre>
                              </>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <AddMember open={adding} onClose={() => setAdding(false)} onAdded={(m) => { setAdding(false); toast(`Added ${m.email}`); load() }} />
    </div>
  )
}

function AddMember({ open, onClose, onAdded }) {
  const toast = useToast()
  const [form, setForm] = useState({ email: '', password: '', role: 'member' })

  async function add(e) {
    e.preventDefault()
    try {
      const member = await api.addMember(form.email, form.password, form.role)
      setForm({ email: '', password: '', role: 'member' })
      onAdded(member)
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  return (
    <Drawer open={open} title="Add a member" onClose={onClose}>
      <form className="form" onSubmit={add}>
        <label className="field">Email
          <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </label>
        <label className="field">Temporary password
          <input type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} />
          <span className="hint">Share it with them directly. At least 8 characters.</span>
        </label>
        <fieldset className="field">
          <legend>Role</legend>
          <div className="role-picker">
            {[['member', 'Member', 'Works on tasks, asks docs, drafts plans'], ['admin', 'Admin', 'Also approves AI plans and adds people']].map(([key, label, text]) => (
              <label key={key} className={`role-option ${form.role === key ? 'on' : ''}`}>
                <input type="radio" name="role" value={key} checked={form.role === key} onChange={() => setForm({ ...form, role: key })} />
                <strong>{label}</strong><span>{text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="form-actions">
          <span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary">Add member</button>
        </div>
      </form>
    </Drawer>
  )
}
