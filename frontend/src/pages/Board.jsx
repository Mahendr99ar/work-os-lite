import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { Avatar, Drawer, EmptyState, Icon, STATUSES, dueInfo, nameFromEmail, useToast } from '../ui.jsx'
import { PageSkeleton } from './Overview.jsx'

function projectFromHash() {
  const id = new URLSearchParams(window.location.hash.split('?')[1] || '').get('project')
  return id ? Number(id) : null
}

export default function Board() {
  const toast = useToast()
  const [projects, setProjects] = useState(null)
  const [projectId, setProjectId] = useState(projectFromHash)
  const [tasks, setTasks] = useState([])
  const [members, setMembers] = useState([])
  const [editing, setEditing] = useState(null) // a task, or {} for a new one
  const [creatingProject, setCreatingProject] = useState(false)
  const [dragOver, setDragOver] = useState(null)

  useEffect(() => {
    Promise.all([api.projects(), api.members()]).then(([list, people]) => {
      setProjects(list)
      setMembers(people)
      setProjectId((current) => (list.some((p) => p.id === current) ? current : list[0]?.id ?? null))
    }).catch((e) => toast(e.message, 'error'))
  }, [toast])

  const loadTasks = useCallback(() => {
    if (!projectId) return
    api.tasks(projectId).then(setTasks).catch((e) => toast(e.message, 'error'))
  }, [projectId, toast])

  useEffect(() => {
    loadTasks()
    if (projectId) window.history.replaceState(null, '', `#/board?project=${projectId}`)
  }, [projectId, loadTasks])

  const byId = useMemo(() => Object.fromEntries(tasks.map((t) => [t.id, t])), [tasks])
  const emailOf = (id) => members.find((m) => m.id === id)?.email

  async function move(task, status) {
    if (task.status === status) return
    setTasks((list) => list.map((t) => (t.id === task.id ? { ...t, status } : t))) // show it moved right away
    try {
      await api.updateTask(task.id, { status })
      toast(`Moved "${task.title}" to ${STATUSES.find((s) => s.key === status).label}`)
    } catch (e) {
      toast(e.message, 'error')
      loadTasks()
    }
  }

  if (!projects) return <PageSkeleton />

  const project = projects.find((p) => p.id === projectId)

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>Board</h1>
          <p className="lede">Drag a card to change its status, or open it to edit the details.</p>
        </div>
        <div className="head-actions">
          {projects.length > 0 && (
            <select className="select-project" value={projectId ?? ''} onChange={(e) => setProjectId(Number(e.target.value))}
                    aria-label="Project">
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
          <button className="btn" onClick={() => setCreatingProject(true)}><Icon name="plus" size={16} />Project</button>
          {project && <button className="btn btn-primary" onClick={() => setEditing({})}><Icon name="plus" size={16} />Task</button>}
        </div>
      </header>

      {!project ? (
        <EmptyState title="Create your first project." action={<button className="btn btn-primary" onClick={() => setCreatingProject(true)}>Create a project</button>}>
          A project holds tasks. You can also let the AI planner draft the tasks for you.
        </EmptyState>
      ) : (
        <div className="board">
          {STATUSES.map((col) => {
            const items = tasks.filter((t) => t.status === col.key)
            return (
              <section key={col.key} className={`column c-${col.key} ${dragOver === col.key ? 'is-over' : ''}`}
                       onDragOver={(e) => { e.preventDefault(); setDragOver(col.key) }}
                       onDragLeave={() => setDragOver(null)}
                       onDrop={(e) => {
                         e.preventDefault()
                         setDragOver(null)
                         const task = byId[Number(e.dataTransfer.getData('text/plain'))]
                         if (task) move(task, col.key)
                       }}>
                <header className="column-head">
                  <span className={`dot s-${col.key}`} />
                  <h2>{col.label}</h2>
                  <span className="count">{items.length}</span>
                </header>
                <div className="column-body">
                  {items.map((t) => {
                    const parent = t.depends_on_id ? byId[t.depends_on_id] : null
                    const waiting = parent && parent.status !== 'done' && t.status !== 'done'
                    const due = dueInfo(t.due_date, t.status)
                    return (
                      <article key={t.id} className={`card ${waiting ? 'is-waiting' : ''}`} draggable
                               onDragStart={(e) => e.dataTransfer.setData('text/plain', String(t.id))}
                               onClick={() => setEditing(t)}
                               onKeyDown={(e) => e.key === 'Enter' && setEditing(t)}
                               tabIndex={0} aria-label={`${t.title}, ${col.label}`}>
                        <div className="card-title">{t.title}</div>
                        {waiting && (
                          <div className="card-wait"><Icon name="link" size={14} />Waiting on {parent.title}</div>
                        )}
                        {(due || t.assignee_id) && (
                          <div className="card-foot">
                            {due ? <span className={`due due-${due.tone}`}>{due.label}</span> : <span />}
                            {t.assignee_id && emailOf(t.assignee_id) && <Avatar email={emailOf(t.assignee_id)} size={22} />}
                          </div>
                        )}
                      </article>
                    )
                  })}
                  {items.length === 0 && <div className="column-empty">Drop a card here</div>}
                </div>
              </section>
            )
          })}
        </div>
      )}

      <TaskDrawer task={editing} tasks={tasks} members={members} projectId={projectId}
                  onClose={() => setEditing(null)}
                  onSaved={(message) => { setEditing(null); toast(message); loadTasks() }} />

      <ProjectDrawer open={creatingProject} onClose={() => setCreatingProject(false)}
                     onCreated={(p) => { setProjects([...projects, p]); setProjectId(p.id); setCreatingProject(false); toast(`Created "${p.name}"`) }} />

    </div>
  )
}

const BLANK = { title: '', description: '', status: 'todo', assignee_id: '', due_date: '', depends_on_id: '' }

function TaskDrawer({ task, tasks, members, projectId, onClose, onSaved }) {
  const toast = useToast()
  const [form, setForm] = useState(BLANK)
  const [saving, setSaving] = useState(false)
  const isNew = task && !task.id

  useEffect(() => {
    if (!task) return
    setForm(isNew ? BLANK : {
      title: task.title, description: task.description || '', status: task.status,
      assignee_id: task.assignee_id ?? '', due_date: task.due_date ?? '', depends_on_id: task.depends_on_id ?? '',
    })
  }, [task, isNew])

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    const body = {
      title: form.title.trim(), description: form.description, status: form.status,
      assignee_id: form.assignee_id ? Number(form.assignee_id) : null,
      due_date: form.due_date || null,
      depends_on_id: form.depends_on_id ? Number(form.depends_on_id) : null,
    }
    try {
      if (isNew) await api.createTask(projectId, body)
      else await api.updateTask(task.id, body)
      onSaved(isNew ? `Added "${body.title}"` : 'Saved changes')
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (!window.confirm(`Delete "${task.title}"? Tasks that wait on it will no longer wait.`)) return
    try {
      await api.deleteTask(task.id)
      onSaved(`Deleted "${task.title}"`)
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  return (
    <Drawer open={Boolean(task)} title={isNew ? 'New task' : 'Edit task'} onClose={onClose}>
      <form className="form" onSubmit={save}>
        <label className="field">Title
          <input value={form.title} onChange={set('title')} required maxLength={200} placeholder="Build auth service" />
        </label>
        <label className="field">Notes
          <textarea rows={4} value={form.description} onChange={set('description')} maxLength={2000} />
        </label>
        <fieldset className="field">
          <legend>Status</legend>
          <div className="status-picker">
            {STATUSES.map((s) => (
              <label key={s.key} className={`status-option s-${s.key} ${form.status === s.key ? 'on' : ''}`}>
                <input type="radio" name="status" value={s.key} checked={form.status === s.key} onChange={set('status')} />
                <i />{s.label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="field-row">
          <label className="field">Assignee
            <select value={form.assignee_id} onChange={set('assignee_id')}>
              <option value="">Nobody</option>
              {members.map((m) => <option key={m.id} value={m.id}>{nameFromEmail(m.email)}</option>)}
            </select>
          </label>
          <label className="field">Due date
            <input type="date" value={form.due_date} onChange={set('due_date')} />
          </label>
        </div>
        <label className="field">Starts after
          <select value={form.depends_on_id} onChange={set('depends_on_id')}>
            <option value="">Nothing, it can start now</option>
            {tasks.filter((t) => t.id !== task?.id).map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </select>
          <span className="hint">The card shows "Waiting on" until that task is done.</span>
        </label>
        <div className="form-actions">
          {!isNew && <button type="button" className="btn btn-danger" onClick={remove}><Icon name="trash" size={16} />Delete</button>}
          <span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={saving}>{isNew ? 'Add task' : 'Save changes'}</button>
        </div>
      </form>
    </Drawer>
  )
}

function ProjectDrawer({ open, onClose, onCreated }) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  async function create(e) {
    e.preventDefault()
    try {
      const project = await api.createProject(name.trim(), description)
      setName('')
      setDescription('')
      onCreated(project)
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  return (
    <Drawer open={open} title="New project" onClose={onClose}>
      <form className="form" onSubmit={create}>
        <label className="field">Name
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} placeholder="Mobile app launch" />
        </label>
        <label className="field">What is it for?
          <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000}
                    placeholder="Ship the Android and iOS app on 1 Dec" />
        </label>
        <div className="form-actions">
          <span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary">Create project</button>
        </div>
      </form>
    </Drawer>
  )
}
