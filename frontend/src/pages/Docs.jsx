import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, Icon, timeAgo, useToast } from '../ui.jsx'

const SUGGESTIONS = [
  'How many days of paid leave do we get?',
  'Who approves a deploy if the on-call engineer is away?',
  'How long is the probation period?',
]

export default function Docs({ meta }) {
  const toast = useToast()
  const [documents, setDocuments] = useState(null)
  const [thread, setThread] = useState([])
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [dropping, setDropping] = useState(false)
  const fileInput = useRef(null)
  const end = useRef(null)

  useEffect(() => { load() }, [])
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [thread])

  async function load() {
    try {
      setDocuments(await api.documents())
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  async function upload(files) {
    const list = [...files]
    if (!list.length) return
    setUploading(true)
    for (const file of list) {
      try {
        const doc = await api.upload(file)
        toast(`Added ${doc.filename} (${doc.chunk_count} ${doc.chunk_count === 1 ? 'chunk' : 'chunks'})`)
      } catch (e) {
        toast(`${file.name}: ${e.message}`, 'error')
      }
    }
    setUploading(false)
    load()
  }

  async function ask(text) {
    const q = text.trim()
    if (q.length < 3 || asking) return
    setQuestion('')
    setAsking(true)
    setThread((t) => [...t, { role: 'user', text: q }])
    try {
      const result = await api.ask(q)
      setThread((t) => [...t, { role: 'answer', ...result }])
    } catch (e) {
      setThread((t) => [...t, { role: 'error', text: e.message }])
    } finally {
      setAsking(false)
    }
  }

  async function remove(doc) {
    if (!window.confirm(`Remove ${doc.filename}? Questions will no longer be answered from it.`)) return
    await api.deleteDocument(doc.id)
    toast(`Removed ${doc.filename}`)
    load()
  }

  const hasDocs = documents?.length > 0

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>Ask docs</h1>
          <p className="lede">Answers come only from your team's documents, with the file named. If the documents don't cover it, you get told so.</p>
        </div>
      </header>

      <div className="docs-layout">
        <section className="library">
          <h2 className="section-title">Library</h2>
          <div className={`dropzone ${dropping ? 'is-over' : ''}`}
               onDragOver={(e) => { e.preventDefault(); setDropping(true) }}
               onDragLeave={() => setDropping(false)}
               onDrop={(e) => { e.preventDefault(); setDropping(false); upload(e.dataTransfer.files) }}
               onClick={() => fileInput.current?.click()}
               onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInput.current?.click()}
               role="button" tabIndex={0}>
            <Icon name="upload" size={20} />
            <span>{uploading ? 'Reading and indexing' : 'Drop PDF, .txt or .md files, or click to choose'}</span>
            <span className="hint">Up to 5 MB each. Only your team can search them.</span>
            <input ref={fileInput} type="file" accept=".pdf,.txt,.md" multiple hidden
                   onChange={(e) => { upload(e.target.files); e.target.value = '' }} />
          </div>

          {documents === null ? <div className="skeleton sk-block" /> : (
            <ul className="doc-list">
              {documents.map((d) => (
                <li key={d.id}>
                  <Icon name="file" size={16} />
                  <div className="doc-text">
                    <div className="doc-name">{d.filename}</div>
                    <div className="doc-meta">{d.chunk_count} {d.chunk_count === 1 ? 'chunk' : 'chunks'}, added {timeAgo(d.created_at)}</div>
                  </div>
                  <button className="icon-btn" onClick={() => remove(d)} aria-label={`Remove ${d.filename}`}><Icon name="trash" size={16} /></button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="chat">
          <div className="chat-scroll">
            {thread.length === 0 ? (
              hasDocs ? (
                <div className="chat-start">
                  {documents.some((d) => d.filename === 'leave_policy.md') ? (
                    <>
                      <p>Try one of these, or ask your own question.</p>
                      <div className="suggestions">
                        {SUGGESTIONS.map((s) => <button key={s} className="suggestion" onClick={() => ask(s)}>{s}</button>)}
                      </div>
                    </>
                  ) : <p>Ask anything your documents cover. Each answer names the file it came from.</p>}
                </div>
              ) : documents !== null && (
                <EmptyState title="Add a document to start asking.">Policies, runbooks and onboarding notes work well.</EmptyState>
              )
            ) : thread.map((m, i) => <Message key={i} message={m} />)}
            {asking && <div className="msg msg-answer is-loading"><span /><span /><span /></div>}
            <div ref={end} />
          </div>

          <form className="chat-input" onSubmit={(e) => { e.preventDefault(); ask(question) }}>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about your documents"
                   aria-label="Question" disabled={!hasDocs || meta?.llm_configured === false} maxLength={1000} />
            <button className="btn btn-primary" disabled={asking || question.trim().length < 3} aria-label="Ask">
              <Icon name="send" size={16} />Ask
            </button>
          </form>
        </section>
      </div>
    </div>
  )
}

function Message({ message }) {
  if (message.role === 'user') return <div className="msg msg-user">{message.text}</div>
  if (message.role === 'error') return <div className="msg msg-error"><Icon name="alert" size={16} />{message.text}</div>
  if (message.refused) {
    return (
      <div className="msg msg-refused">
        <div className="msg-label">Not in your documents</div>
        <p>None of your team's files answer this, so no answer was made up. Upload a document that covers it and ask again.</p>
      </div>
    )
  }
  return (
    <div className="msg msg-answer">
      <p>{message.answer}</p>
      <div className="sources">
        {message.sources.map((s) => (
          <span key={s.document_id} className="source" title={`Match score ${s.similarity}`}>
            <Icon name="file" size={14} />{s.filename}
          </span>
        ))}
      </div>
    </div>
  )
}
