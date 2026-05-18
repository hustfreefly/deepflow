import { useState, useEffect } from 'react'

interface SystemInfo {
  openclaw: { status: string; version: string }
  backend: { version: string; host: string; port: number }
  blackboard: { path: string; session_count: number }
  config: { webhook_url: string; frontend_port: number; backend_port: number }
}

interface SettingsDialogProps {
  onClose: () => void
}

const SettingsDialog: React.FC<SettingsDialogProps> = ({ onClose }) => {
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v2/system-info')
      .then(r => r.json())
      .then(d => setSystemInfo(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const statusBadge = (status: string) => {
    const color = status === 'connected' || status === 'ok' || status === 'running' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
    const label = status === 'connected' ? '已连接' : status === 'ok' ? '正常' : status === 'running' ? '运行中' : status
    return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>{label}</span>
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-medium text-onsurface">系统设置</h2>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-surface-variant flex items-center justify-center transition-colors">
            <span className="material-icons-round text-sm text-onsurface-variant">close</span>
          </button>
        </div>

        {loading ? (
          <div className="text-center py-8 text-onsurface-variant">加载系统信息...</div>
        ) : systemInfo ? (
          <div className="space-y-6">
            {/* OpenClaw 连接 */}
            <div>
              <h3 className="text-sm font-medium text-onsurface mb-3 flex items-center gap-2">
                <span className="material-icons-round text-sm text-primary-600">hub</span>
                OpenClaw 连接
              </h3>
              <div className="bg-surface-variant rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">状态</span>
                  {statusBadge(systemInfo.openclaw.status)}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">版本</span>
                  <span className="text-sm font-mono text-onsurface">{systemInfo.openclaw.version}</span>
                </div>
              </div>
            </div>

            {/* 后端 API */}
            <div>
              <h3 className="text-sm font-medium text-onsurface mb-3 flex items-center gap-2">
                <span className="material-icons-round text-sm text-green-600">dns</span>
                后端 API
              </h3>
              <div className="bg-surface-variant rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">状态</span>
                  {statusBadge(systemInfo.backend.version ? 'ok' : 'error')}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">地址</span>
                  <span className="text-sm font-mono text-onsurface">{systemInfo.backend.host}:{systemInfo.backend.port}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">API 版本</span>
                  <span className="text-sm font-mono text-onsurface">{systemInfo.backend.version}</span>
                </div>
              </div>
            </div>

            {/* 管线配置 */}
            <div>
              <h3 className="text-sm font-medium text-onsurface mb-3 flex items-center gap-2">
                <span className="material-icons-round text-sm text-purple-600">settings</span>
                管线配置
              </h3>
              <div className="bg-surface-variant rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">前端端口</span>
                  <span className="text-sm font-mono text-onsurface">{systemInfo.config.frontend_port}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">后端端口</span>
                  <span className="text-sm font-mono text-onsurface">{systemInfo.config.backend_port}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">Webhook</span>
                  <span className="text-xs font-mono text-onsurface truncate max-w-[200px]">{systemInfo.config.webhook_url}</span>
                </div>
              </div>
            </div>

            {/* 数据存储 */}
            <div>
              <h3 className="text-sm font-medium text-onsurface mb-3 flex items-center gap-2">
                <span className="material-icons-round text-sm text-orange-600">folder</span>
                数据存储
              </h3>
              <div className="bg-surface-variant rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">Blackboard 路径</span>
                </div>
                <div className="text-xs font-mono text-onsurface bg-white rounded-lg p-2 break-all">
                  {systemInfo.blackboard.path}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-onsurface-variant">任务数</span>
                  <span className="text-sm font-medium text-onsurface">{systemInfo.blackboard.session_count} 个</span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-red-600">系统信息加载失败</div>
        )}
      </div>
    </div>
  )
}

export default SettingsDialog
