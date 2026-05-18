import { getPollingConfig } from "./config/defaults"
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from './components/Header'


interface HealthResponse {
  status: string
  version: string
  openclaw: {
    status: string
    details: string
  }
}

function App() {
  const navigate = useNavigate()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch('/api/health')
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const data = await response.json()
        setHealth(data)
      } catch (err) {
        setHealth({
          status: 'error',
          version: '0.1.0',
          openclaw: { status: 'unknown', details: err instanceof Error ? err.message : 'Network error' }
        })
      } finally {
        setLoading(false)
      }
    }

    checkHealth()
    const interval = setInterval(checkHealth, getPollingConfig().health_ms)
    return () => clearInterval(interval)
  }, [])

  const isOpenclawConnected = health?.openclaw?.status === 'connected'

  // Active task state (pipeline status card)
  const [activeTask, setActiveTask] = useState<{
    session_id: string
    domain: string
    status: string
    topic?: string
    code?: string
    name?: string
  } | null>(null)

  useEffect(() => {
    const fetchActiveTask = async () => {
      try {
        const response = await fetch('/api/v2/active-task')
        if (response.ok) {
          const data = await response.json()
          setActiveTask(data)
        }
      } catch {
        // Silently ignore
      }
    }

    fetchActiveTask()
    // Poll every 5 seconds for active task updates
    const interval = setInterval(fetchActiveTask, getPollingConfig().active_task_ms)
    return () => clearInterval(interval)
  }, [])

  const [online, setOnline] = useState(true)

  useEffect(() => {
    const handleOnline = () => setOnline(true)
    const handleOffline = () => setOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    setOnline(navigator.onLine)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return (
    <div className="min-h-screen bg-surface-variant">
      {!online && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-2 text-center">
          <span className="material-icons-round text-red-600 text-sm align-middle mr-1">wifi_off</span>
          <span className="text-sm text-red-700">网络已断开，请检查网络连接</span>
        </div>
      )}
      <Header 
        openclawStatus={health?.openclaw?.status || 'unknown'}
        apiStatus={health?.status || 'error'}
        version={health?.version || '0.1.0'}
        loading={loading}
      />
      
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Pipeline Status Card - shows active task */}
        {activeTask && (
          <div className="bg-white rounded-2xl p-6 mb-6 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group"
               onClick={() => navigate(`/progress/${activeTask.session_id}`)}>
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center flex-shrink-0 bg-gradient-to-br ${
                  activeTask.status === 'running' ? 'from-primary-50 to-primary-100' :
                  activeTask.status === 'waiting_agent' ? 'from-yellow-50 to-yellow-100' :
                  'from-green-50 to-emerald-100'
                }`}>
                  <span className={`material-icons-round text-3xl ${
                    activeTask.status === 'running' ? 'text-primary-600 animate-spin' :
                    activeTask.status === 'waiting_agent' ? 'text-yellow-600' :
                    'text-green-600'
                  }`}>
                    {activeTask.status === 'running' ? 'sync' :
                     activeTask.status === 'waiting_agent' ? 'hourglass_top' :
                     'check_circle'}
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h2 className="text-lg font-medium text-onsurface">
                      {activeTask.topic || activeTask.name || activeTask.code || '任务执行中'}
                    </h2>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      activeTask.status === 'running' ? 'bg-primary-100 text-primary-700' :
                      activeTask.status === 'waiting_agent' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-green-100 text-green-700'
                    }`}>
                      {activeTask.status === 'running' ? '执行中' :
                       activeTask.status === 'waiting_agent' ? '排队中' :
                       '已完成'}
                    </span>
                  </div>
                  <p className="text-sm text-onsurface-variant font-mono">
                    {activeTask.session_id}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-primary-600 group-hover:gap-3 transition-all duration-200">
                <span className="text-sm font-medium">查看进度</span>
                <span className="material-icons-round">chevron_right</span>
              </div>
            </div>
          </div>
        )}

        {/* Welcome Section */}
        <div className="bg-white rounded-2xl p-8 mb-6 shadow-sm border border-outline-variant/50">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 bg-gradient-to-br from-primary-50 to-primary-100 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-sm">
              <span className="material-icons-round text-primary-600 text-3xl">analytics</span>
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-onsurface mb-2">
                欢迎使用 DeepFlow
              </h1>
              <p className="text-onsurface-variant leading-relaxed">
                基于 OpenClaw 的多Agent协作管线可视化平台。
                选择下方的已适配场景任务。
              </p>
            </div>
          </div>
        </div>

        {/* Domain Cards */}
        <div className="mb-6">
          <h2 className="text-lg font-medium text-onsurface mb-4 flex items-center gap-2">
            <span className="material-icons-round text-onsurface-variant">category</span>
            选择任务类型
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Solution Pro */}
            <div 
              onClick={() => isOpenclawConnected && navigate('/task/solution')}
              className={`bg-white rounded-2xl p-6 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group ${
                !isOpenclawConnected ? 'opacity-50 pointer-events-none' : ''
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-primary-50 to-primary-100 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform duration-200 shadow-sm">
                  <span className="material-icons-round text-primary-600 text-3xl">architecture</span>
                </div>
                <span className="px-2 py-1 bg-primary-100 text-primary-700 text-xs font-medium rounded-full">核心模块</span>
              </div>
              <h3 className="text-lg font-semibold text-onsurface mb-1">Solution Pro</h3>
              <div className="mb-4">
                <p className="text-sm text-onsurface-variant">输出高质量解决方案</p>
                <p className="text-xs text-onsurface-variant/70 mt-1">场景：架构设计，方案制定，复杂场景咨询</p>
              </div>
              <button className="flex items-center gap-2 text-primary-600 text-sm font-medium group-hover:gap-3 transition-all duration-200">
                开始设计
                <span className="material-icons-round text-sm">arrow_forward</span>
              </button>
            </div>

            {/* Investment */}
            <div className="bg-surface-variant rounded-2xl p-6 border border-outline-variant opacity-60 cursor-not-allowed">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center">
                  <span className="material-icons-round text-gray-400 text-3xl">trending_up</span>
                </div>
                <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs font-medium rounded-full">即将推出</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-500 mb-1">投资分析</h3>
              <p className="text-sm text-gray-400 mb-4">股票、基金、行业深度分析</p>
              <button disabled className="flex items-center gap-2 text-gray-400 text-sm font-medium cursor-not-allowed">
                敬请期待
                <span className="material-icons-round text-sm">lock</span>
              </button>
            </div>

            {/* Coming Soon */}
            <div className="bg-surface-variant rounded-2xl p-6 border border-outline-variant opacity-60 cursor-not-allowed">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center">
                  <span className="material-icons-round text-gray-400 text-3xl">code</span>
                </div>
                <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs font-medium rounded-full">即将推出</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-500 mb-1">代码审查</h3>
              <p className="text-sm text-gray-400 mb-4">PR 自动化审查、安全扫描</p>
              <button disabled className="flex items-center gap-2 text-gray-400 text-sm font-medium cursor-not-allowed">
                敬请期待
                <span className="material-icons-round text-sm">lock</span>
              </button>
            </div>
          </div>
        </div>

        {/* Warning */}
        {!isOpenclawConnected && !loading && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-4 flex items-start gap-3">
            <span className="material-icons-round text-yellow-600 mt-0.5">warning</span>
            <div>
              <p className="text-sm font-medium text-yellow-800">OpenClaw 未连接</p>
              <p className="text-xs text-yellow-700 mt-1">请确保 OpenClaw 已安装并运行后再试。</p>
            </div>
          </div>
        )}
      </main>

      {/* FAB */}
      <button
        onClick={() => isOpenclawConnected && navigate('/task/solution')}
        className={`fixed bottom-8 right-8 w-14 h-14 bg-primary-600 text-white rounded-2xl shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 transition-all duration-200 flex items-center justify-center ${
          !isOpenclawConnected ? 'opacity-50 pointer-events-none' : ''
        }`}
      >
        <span className="material-icons-round text-2xl">add</span>
      </button>
    </div>
  )
}

export default App