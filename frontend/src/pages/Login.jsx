import { useState } from 'react'
import { api, tokenStore } from '../api.js'

export default function Login({ meta, onLogin }) {
  const [mode, setMode] = useState('login')
  const [teamName, setTeamName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  async function finish(promise, which) {
    setError('')
    setBusy(which)
    try {
      const { access_token } = await promise()
      tokenStore.set(access_token)
      onLogin(await api.me())
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  function submit(e) {
    e.preventDefault()
    finish(() => (mode === 'login' ? api.login(email, password) : api.signup(teamName, email, password)), 'form')
  }

  const demoOn = meta?.demo_mode !== false

  return (
    <div className="login">
      <section className="login-story">
        <div className="login-brand"><span className="logo-mark" aria-hidden="true" />Work OS Lite</div>
        <h1>The AI drafts the plan. Your team decides what ships.</h1>
        <p>
          Track projects and tasks, ask questions about your team's documents, and turn a messy brief into a task plan.
          Suggestions stay as drafts until an admin approves them.
        </p>

        <div className="specimen" aria-hidden="true">
          <div className="specimen-card draft">
            <span className="specimen-tag">AI draft</span>
            <strong>Integrate payments</strong>
            <span>Starts after: Build login</span>
          </div>
          <div className="specimen-arrow">Approved by Riya</div>
          <div className="specimen-card solid">
            <span className="specimen-tag">On the board</span>
            <strong>Integrate payments</strong>
            <span>Starts after: Build login</span>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-form" onSubmit={submit}>
          <div className="segmented" role="tablist">
            <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'on' : ''}
                    onClick={() => setMode('login')}>Log in</button>
            <button type="button" role="tab" aria-selected={mode === 'signup'} className={mode === 'signup' ? 'on' : ''}
                    onClick={() => setMode('signup')}>Create a team</button>
          </div>

          {mode === 'signup' && (
            <label className="field">Team name
              <input value={teamName} onChange={(e) => setTeamName(e.target.value)} required minLength={2}
                     placeholder="Acme Mobile" autoComplete="organization" />
            </label>
          )}
          <label className="field">Work email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          <label className="field">Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8}
                   autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
            {mode === 'signup' && <span className="hint">At least 8 characters. You become the team's admin.</span>}
          </label>

          {error && <div className="form-error" role="alert">{error}</div>}

          <button className="btn btn-primary btn-block" disabled={Boolean(busy)}>
            {busy === 'form' ? 'One moment' : mode === 'login' ? 'Log in' : 'Create team'}
          </button>

          {demoOn && (
            <div className="demo-box">
              <button type="button" className="btn btn-block" disabled={Boolean(busy)}
                      onClick={() => finish(api.demo, 'demo')}>
                {busy === 'demo' ? 'Setting up your sandbox' : 'Open a demo workspace'}
              </button>
              <p>A private sandbox with two projects, three policy documents and one AI plan waiting for review. No sign-up.</p>
            </div>
          )}
        </form>
      </section>
    </div>
  )
}
