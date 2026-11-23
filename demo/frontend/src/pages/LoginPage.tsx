import { useState } from 'react'
import { api } from '../api'
import { Icon } from '../components/Icon'
import type { Me } from '../types'

/** Trang đăng nhập. Tài khoản do quản trị khai báo trong demo/backend/.env. */
export function LoginPage({ onLogin }: { onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(username, password)
      onLogin(await api.me())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <form className="card login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="brand">
          <Icon name="shield" size={24} />
          <div>
            <h1 id="login-title">Giám sát đám đông</h1>
            <span className="sub">Đăng nhập để tiếp tục</span>
          </div>
        </div>
        <label className="field">
          <span>Tên đăng nhập</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label className="field">
          <span>Mật khẩu</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password" required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Đang đăng nhập…' : 'Đăng nhập'}</button>
      </form>
    </main>
  )
}
