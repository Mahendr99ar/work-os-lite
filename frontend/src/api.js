// Every call to the backend goes through this file.
// The JWT is kept in localStorage and sent as a Bearer token.

const BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export const tokenStore = {
  get: () => {
    try { return localStorage.getItem('token') } catch { return null }
  },
  set: (t) => {
    try { localStorage.setItem('token', t) } catch { /* private mode: token lives for this tab only */ }
  },
  clear: () => {
    try { localStorage.removeItem('token') } catch { /* ignore */ }
  },
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(path, { method = 'GET', body, form, file } = {}) {
  const headers = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (file) {
    payload = new FormData()
    payload.append('file', file)
  } else if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(form)
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(BASE_URL + path, { method, headers, body: payload })
  } catch {
    // Free hosts sleep when idle. The first request after a break can take up to a minute.
    throw new ApiError('Cannot reach the server. If it was asleep, it is waking up: try again in 30 seconds.', 0)
  }

  if (res.status === 401 && token && path !== '/auth/login') {
    tokenStore.clear()
    window.dispatchEvent(new Event('workos:logout'))
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => `${d.loc?.at(-1) ?? 'field'}: ${d.msg}`).join(', ')
      : data.detail
    throw new ApiError(detail || `Request failed (${res.status})`, res.status)
  }
  return data
}

export const api = {
  meta: () => request('/meta'),

  signup: (team_name, email, password) => request('/auth/signup', { method: 'POST', body: { team_name, email, password } }),
  login: (email, password) => request('/auth/login', { method: 'POST', form: { username: email, password } }),
  demo: () => request('/auth/demo', { method: 'POST' }),
  me: () => request('/auth/me'),

  members: () => request('/team/members'),
  addMember: (email, password, role) => request('/team/members', { method: 'POST', body: { email, password, role } }),

  projects: () => request('/projects'),
  createProject: (name, description) => request('/projects', { method: 'POST', body: { name, description } }),
  updateProject: (id, changes) => request(`/projects/${id}`, { method: 'PATCH', body: changes }),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),

  allTasks: () => request('/tasks'),
  tasks: (projectId) => request(`/projects/${projectId}/tasks`),
  createTask: (projectId, task) => request(`/projects/${projectId}/tasks`, { method: 'POST', body: task }),
  updateTask: (id, changes) => request(`/tasks/${id}`, { method: 'PATCH', body: changes }),
  deleteTask: (id) => request(`/tasks/${id}`, { method: 'DELETE' }),
  blocked: () => request('/tasks/blocked'),

  documents: () => request('/documents'),
  upload: (file) => request('/documents', { method: 'POST', file }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  ask: (question) => request('/ask', { method: 'POST', body: { question } }),

  plans: () => request('/planner/plans'),
  createPlan: (project_id, brief) => request('/planner/plans', { method: 'POST', body: { project_id, brief } }),
  approvePlan: (id) => request(`/planner/plans/${id}/approve`, { method: 'POST' }),
  rejectPlan: (id) => request(`/planner/plans/${id}/reject`, { method: 'POST' }),

  audit: () => request('/audit'),
}
