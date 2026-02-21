import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  type AdminUserSummary,
  type OverviewResponse,
  type SheetDetail,
  type AdminUser,
  type ListUsersResponse,
  getOverview,
  getStreamUrl,
  getUserDetail,
  login,
  listUsers,
  createUser,
  deleteUser,
  resetPassword,
} from './api';

type AdminIdentity = {
  id: string;
  username: string;
  display_name?: string | null;
  role?: string;
};

type StreamStatus = 'connecting' | 'online' | 'offline';
type TabType = 'progress' | 'users';

function todayISODate(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatPercent(value: number): string {
  return `${(Math.max(0, Math.min(1, value)) * 100).toFixed(1)}%`;
}

function formatTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function deriveKpis(users: AdminUserSummary[]): OverviewResponse['kpis'] {
  const activeUserCount = users.length;
  const updatedSheetCount = users.reduce((acc, item) => acc + item.today_updated_sheet_count, 0);
  const totalRows = users.reduce((acc, item) => acc + item.today_total_rows, 0);
  const quotedRows = users.reduce((acc, item) => acc + item.today_quoted_rows, 0);
  return {
    active_user_count: activeUserCount,
    updated_sheet_count: updatedSheetCount,
    total_rows: totalRows,
    quoted_rows: quotedRows,
    overall_progress: totalRows > 0 ? quotedRows / totalRows : 0,
  };
}

function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('admin_token'));
  const [admin, setAdmin] = useState<AdminIdentity | null>(() => {
    const raw = localStorage.getItem('admin_user');
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AdminIdentity;
    } catch {
      return null;
    }
  });
  const [date, setDate] = useState(todayISODate);
  const [tz] = useState('Asia/Shanghai');
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('offline');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [overview, setOverview] = useState<OverviewResponse>({
    date: todayISODate(),
    tz,
    kpis: {
      active_user_count: 0,
      updated_sheet_count: 0,
      total_rows: 0,
      quoted_rows: 0,
      overall_progress: 0,
    },
    users: [],
  });
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [selectedUser, setSelectedUser] = useState<AdminUserSummary | null>(null);
  const [sheetDetails, setSheetDetails] = useState<SheetDetail[]>([]);

  // Tab 和用户管理状态
  const [activeTab, setActiveTab] = useState<TabType>('progress');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersPagination, setUsersPagination] = useState({ total: 0, page: 1, pageSize: 20 });

  const loadOverview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const data = await getOverview(date, tz);
      setOverview(data);
      setSelectedUserId((prev) => (!prev && data.users.length > 0 ? data.users[0].user_id : prev));
    } catch (err) {
      setError((err as Error).message || '加载总览失败');
    } finally {
      setLoading(false);
    }
  }, [date, token, tz]);

  const loadUserDetail = useCallback(
    async (userId: string) => {
      if (!token || !userId) return;
      try {
        const data = await getUserDetail(userId, date, tz);
        setSelectedUser(data.user);
        setSheetDetails(data.sheets);
      } catch {
        setSelectedUser(null);
        setSheetDetails([]);
      }
    },
    [date, token, tz],
  );

  const loadUsers = useCallback(async (page = 1) => {
    if (!token) return;
    setUsersLoading(true);
    try {
      const data = await listUsers(page, usersPagination.pageSize);
      setUsers(data.users);
      setUsersPagination({ total: data.total, page: data.page, pageSize: data.page_size });
    } catch {
      setError('加载用户列表失败');
    } finally {
      setUsersLoading(false);
    }
  }, [token, usersPagination.pageSize]);

  useEffect(() => {
    if (!token) return;
    void loadOverview();
  }, [loadOverview, token]);

  useEffect(() => {
    if (activeTab === 'users') {
      void loadUsers();
    }
  }, [activeTab, loadUsers]);

  useEffect(() => {
    if (!selectedUserId) return;
    void loadUserDetail(selectedUserId);
  }, [loadUserDetail, selectedUserId]);

  const selectedUserIdRef = useRef(selectedUserId);
  useEffect(() => {
    selectedUserIdRef.current = selectedUserId;
  }, [selectedUserId]);

  useEffect(() => {
    if (!token) return;
    let source: EventSource | null = null;
    let cancelled = false;
    let retryCount = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = async () => {
      setStreamStatus('connecting');
      try {
        const url = await getStreamUrl(date, tz);
        if (cancelled) return;
        source = new EventSource(url);

        source.addEventListener('ready', () => {
          setStreamStatus('online');
          retryCount = 0;
        });

        source.addEventListener('progress_update', (event) => {
          try {
            const payload = JSON.parse((event as MessageEvent).data) as {
              user?: AdminUserSummary | null;
            };
            const changedUser = payload.user;
            if (!changedUser) return;

            setOverview((prev) => {
              const exists = prev.users.some((item) => item.user_id === changedUser.user_id);
              const nextUsers = exists
                ? prev.users.map((item) => (item.user_id === changedUser.user_id ? changedUser : item))
                : [changedUser, ...prev.users];
              const sortedUsers = [...nextUsers].sort(
                (a, b) =>
                  b.today_progress - a.today_progress || b.today_total_rows - a.today_total_rows,
              );
              return {
                ...prev,
                users: sortedUsers,
                kpis: deriveKpis(sortedUsers),
              };
            });

            if (selectedUserIdRef.current === changedUser.user_id) {
              void loadUserDetail(changedUser.user_id);
            }
          } catch {
            // Ignore malformed SSE payloads.
          }
        });

        source.onerror = () => {
          setStreamStatus('offline');
          source?.close();
          if (!cancelled && retryCount < 5) {
            const delay = Math.min(1000 * 2 ** retryCount, 30000);
            retryCount++;
            retryTimer = setTimeout(() => void connect(), delay);
          }
        };
      } catch {
        setStreamStatus('offline');
        if (!cancelled && retryCount < 5) {
          const delay = Math.min(1000 * 2 ** retryCount, 30000);
          retryCount++;
          retryTimer = setTimeout(() => void connect(), delay);
        }
      }
    };

    void connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      source?.close();
      setStreamStatus('offline');
    };
  }, [date, loadUserDetail, token, tz]);

  const displayUsers = useMemo(() => overview.users, [overview.users]);

  const handleLogin = async (username: string, password: string) => {
    setError('');
    setLoading(true);
    try {
      const result = await login(username, password);
      const role = (result.user.role || 'user').toLowerCase();
      if (role !== 'admin') {
        setError('该账号不是管理员，无法进入管理面板。');
        return;
      }
      localStorage.setItem('admin_token', result.access_token);
      localStorage.setItem('admin_user', JSON.stringify(result.user));
      setToken(result.access_token);
      setAdmin(result.user);
    } catch (err) {
      setError((err as Error).message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_user');
    setToken(null);
    setAdmin(null);
    setOverview((prev) => ({ ...prev, users: [] }));
    setSelectedUserId('');
    setSelectedUser(null);
    setSheetDetails([]);
  };

  if (!token || !admin) {
    return (
      <LoginScreen loading={loading} error={error} onSubmit={handleLogin} />
    );
  }

  return (
    <div className="page">
      <div className="orb orb-left" />
      <div className="orb orb-right" />

      <header className="topbar">
        <div>
          <p className="eyebrow">SmartProcure Admin</p>
          <h1>管理控制台</h1>
        </div>
        <div className="topbar-actions">
          <div className="tab-switch">
            <button className={activeTab === 'progress' ? 'active' : ''} onClick={() => setActiveTab('progress')}>进度监控</button>
            <button className={activeTab === 'users' ? 'active' : ''} onClick={() => setActiveTab('users')}>用户管理</button>
          </div>
          <label className="date-picker">
            <span>统计日期</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <button className="btn-secondary" onClick={() => void loadOverview()}>刷新</button>
          <span className={`stream-badge ${streamStatus}`}>{streamStatus}</span>
          <div className="admin-pill">
            <strong>{admin.display_name || admin.username}</strong>
            <button onClick={handleLogout}>退出</button>
          </div>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      {activeTab === 'progress' && (
        <>
          <section className="kpi-grid">
        <KpiCard label="今日活跃账号" value={overview.kpis.active_user_count.toString()} />
        <KpiCard label="今日更新表格" value={overview.kpis.updated_sheet_count.toString()} />
        <KpiCard label="询价产品总行数" value={overview.kpis.total_rows.toString()} mono />
        <KpiCard
          label="已报价产品行数"
          value={`${overview.kpis.quoted_rows} (${formatPercent(overview.kpis.overall_progress)})`}
          mono
        />
      </section>

      <section className="content-grid">
        <div className="panel">
          <div className="panel-header">
            <h2>账号进度排行</h2>
            <span>{displayUsers.length} 个账号</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  <th>今日表格名称</th>
                  <th>进度</th>
                  <th>已报价/总行</th>
                  <th>今日更新表格</th>
                  <th>最近更新时间</th>
                </tr>
              </thead>
              <tbody>
                {displayUsers.map((item) => {
                  const active = item.user_id === selectedUserId;
                  return (
                    <tr
                      key={item.user_id}
                      className={active ? 'active' : ''}
                      onClick={() => setSelectedUserId(item.user_id)}
                    >
                      <td>{item.display_name || item.username}</td>
                      <td>
                        <div className="sheet-name-list">
                          {(item.updated_sheet_names || []).slice(0, 2).map((name) => (
                            <span key={`${item.user_id}-${name}`} className="sheet-pill" title={name}>
                              {name}
                            </span>
                          ))}
                          {(item.updated_sheet_names || []).length > 2 ? (
                            <span className="sheet-pill more">+{(item.updated_sheet_names || []).length - 2}</span>
                          ) : null}
                          {(item.updated_sheet_names || []).length === 0 ? (
                            <span className="sheet-pill empty">-</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="progress-cell">
                          <div className="progress-track">
                            <div style={{ width: `${Math.round(item.today_progress * 100)}%` }} />
                          </div>
                          <span>{formatPercent(item.today_progress)}</span>
                        </div>
                      </td>
                      <td className="mono">{item.today_quoted_rows} / {item.today_total_rows}</td>
                      <td>{item.today_updated_sheet_count}</td>
                      <td>{formatTime(item.last_update_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>账号表格明细</h2>
            <span>{selectedUser ? (selectedUser.display_name || selectedUser.username) : '未选择'}</span>
          </div>
          <div className="detail-summary">
            <div>
              <label>总行数</label>
              <strong>{selectedUser?.today_total_rows ?? 0}</strong>
            </div>
            <div>
              <label>已报价行</label>
              <strong>{selectedUser?.today_quoted_rows ?? 0}</strong>
            </div>
            <div>
              <label>进度</label>
              <strong>{formatPercent(selectedUser?.today_progress ?? 0)}</strong>
            </div>
          </div>
          <div className="sheet-list">
            {sheetDetails.map((sheet) => (
              <article key={sheet.sheet_id} className="sheet-card">
                <div className="sheet-head">
                  <h3>{sheet.sheet_name}</h3>
                  <span>{formatPercent(sheet.progress)}</span>
                </div>
                <p>已报价 {sheet.quoted_rows} / 总行 {sheet.total_rows}</p>
                <small>更新时间: {formatTime(sheet.updated_at)}</small>
              </article>
            ))}
            {sheetDetails.length === 0 ? <p className="empty-tip">当前用户当天暂无更新表格。</p> : null}
          </div>
        </div>
      </section>
        </>
      )}

      {activeTab === 'users' && (
        <UserManagement users={users} loading={usersLoading} pagination={usersPagination} onRefresh={loadUsers} />
      )}
    </div>
  );
}

function LoginScreen(props: {
  loading: boolean;
  error: string;
  onSubmit: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  return (
    <div className="login-page">
      <div className="login-card">
        <p className="eyebrow">Admin Access</p>
        <h1>SmartProcure 管理端</h1>
        <p>请使用管理员账号登录</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void props.onSubmit(username, password);
          }}
        >
          <label>
            账号
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {props.error ? <div className="error-banner">{props.error}</div> : null}
          <button type="submit" disabled={props.loading}>
            {props.loading ? '登录中...' : '进入管理端'}
          </button>
        </form>
      </div>
    </div>
  );
}

function KpiCard(props: { label: string; value: string; mono?: boolean }) {
  return (
    <article className="kpi-card">
      <span>{props.label}</span>
      <strong className={props.mono ? 'mono' : ''}>{props.value}</strong>
    </article>
  );
}

function UserManagement(props: {
  users: AdminUser[];
  loading: boolean;
  pagination: { total: number; page: number; pageSize: number };
  onRefresh: (page?: number) => void;
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', display_name: '', role: 'user' });
  const [resetUserId, setResetUserId] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');

  const handleCreate = async () => {
    if (!form.username || !form.password) return;
    try {
      await createUser({
        username: form.username,
        password: form.password,
        display_name: form.display_name || undefined,
        role: form.role,
      });
      setShowCreate(false);
      setForm({ username: '', password: '', display_name: '', role: 'user' });
      props.onRefresh();
    } catch (e: unknown) {
      alert((e as Error).message || '创建失败');
    }
  };

  const handleDelete = async (userId: string, username: string) => {
    if (!confirm(`确定删除用户 ${username}？`)) return;
    try {
      await deleteUser(userId);
      props.onRefresh();
    } catch (e: unknown) {
      alert((e as Error).message || '删除失败');
    }
  };

  const handleResetPassword = async () => {
    if (!resetUserId || !newPassword) return;
    try {
      await resetPassword(resetUserId, newPassword);
      setResetUserId(null);
      setNewPassword('');
      alert('密码已重置');
    } catch (e: unknown) {
      alert((e as Error).message || '重置失败');
    }
  };

  return (
    <section className="panel" style={{ marginTop: 18 }}>
      <div className="panel-header">
        <h2>用户管理</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" onClick={props.onRefresh}>刷新</button>
          <button className="btn-secondary" onClick={() => setShowCreate(true)}>新建用户</button>
        </div>
      </div>

      {showCreate && (
        <div className="create-form">
          <input placeholder="用户名" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} />
          <input placeholder="密码" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
          <input placeholder="显示名称" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} />
          <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
          <button onClick={handleCreate}>创建</button>
          <button onClick={() => setShowCreate(false)}>取消</button>
        </div>
      )}

      {resetUserId && (
        <div className="create-form">
          <input placeholder="新密码" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} />
          <button onClick={handleResetPassword}>确认重置</button>
          <button onClick={() => setResetUserId(null)}>取消</button>
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>用户名</th>
              <th>显示名称</th>
              <th>角色</th>
              <th>创建时间</th>
              <th>最后登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {props.users.map(u => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>{u.display_name || '-'}</td>
                <td>{u.role === 'admin' ? '管理员' : '普通用户'}</td>
                <td>{formatTime(u.created_at)}</td>
                <td>{formatTime(u.last_login_at)}</td>
                <td>
                  <button className="btn-small" onClick={() => setResetUserId(u.id)}>重置密码</button>
                  <button className="btn-small btn-danger" onClick={() => handleDelete(u.id, u.username)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {props.loading && <p className="empty-tip">加载中...</p>}
        {!props.loading && props.users.length === 0 && <p className="empty-tip">暂无用户</p>}
      </div>
      {props.pagination.total > props.pagination.pageSize && (
        <div className="pagination">
          <button disabled={props.pagination.page <= 1} onClick={() => props.onRefresh(props.pagination.page - 1)}>上一页</button>
          <span>{props.pagination.page} / {Math.ceil(props.pagination.total / props.pagination.pageSize)}</span>
          <button disabled={props.pagination.page >= Math.ceil(props.pagination.total / props.pagination.pageSize)} onClick={() => props.onRefresh(props.pagination.page + 1)}>下一页</button>
        </div>
      )}
    </section>
  );
}

export default App;
