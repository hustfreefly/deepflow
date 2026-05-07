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
    const interval = setInterval(checkHealth, 5000)
    return () => clearInterval(interval)
  }, [])

  const isOpenclawConnected = health?.openclaw?.status === 'connected'

  return (
    <div className="min-h-screen bg-surface-variant">
      <Header 
        openclawStatus={health?.openclaw?.status || 'unknown'}
        apiStatus={health?.status || 'error'}
        version={health?.version || '0.1.0'}
        loading={loading}
      />
      
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Welcome Section */}
        <div className="bg-white rounded-2xl p-8 mb-6 shadow-sm border border-outline-variant">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 bg-primary-50 rounded-2xl flex items-center justify-center flex-shrink-0">
              <span className="material-icons-round text-primary-600 text-3xl">analytics</span>
            </div>
            <div>
              <h1 className="text-2xl font-medium text-onsurface mb-2">
                欢迎使用 DeepFlow
              </h1>
              <p className="text-onsurface-variant leading-relaxed">
                基于 OpenClaw 的多 Agent 分析管线可视化平台。
                选择下方任务类型开始分析。
              </p>
            </div>
          </div>
        </div>

        {/* Domain Cards */}
        <div className="mb-6">
          <h2 className="text-lg font-medium text-onsurface mb-4 flex items-center gap-2">
            <span className="material-icons-round text-onsurface-variant">category</span>
            选择分析类型
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Solution Pro */}
            <div 
              onClick={() => isOpenclawConnected && navigate('/task/solution')}
              className={`bg-white rounded-2xl p-6 shadow-sm border-2 border-primary-200 hover:shadow-md transition-all cursor-pointer group ${
                !isOpenclawConnected ? 'opacity-50 pointer-events-none' : ''
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-primary-50 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                  <span className="material-icons-round text-primary-600 text-2xl">architecture</span>
                </div>
                <span className="px-2 py-1 bg-primary-100 text-primary-700 text-xs font-medium rounded-full">核心模块</span>
              </div>
              <h3 className="text-lg font-medium text-onsurface mb-1">方案设计</h3>
              <p className="text-sm text-onsurface-variant mb-4">通用多 Agent 分析管线，支持任意主题深度研究</p>
              <button className="flex items-center gap-1 text-primary-600 text-sm font-medium group-hover:gap-2 transition-all">
                开始设计
                <span className="material-icons-round text-sm">arrow_forward</span>
              </button>
            </div>

            {/* Investment */}
            <div 
              onClick={() => isOpenclawConnected && navigate('/task/investment')}
              className={`bg-white rounded-2xl p-6 shadow-sm border border-outline-variant hover:shadow-md transition-all cursor-pointer group ${
                !isOpenclawConnected ? 'opacity-50 pointer-events-none' : ''
              }`}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-green-50 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform">
                  <span className="material-icons-round text-green-600 text-2xl">trending_up</span>
                </div>
                <span className="px-2 py-1 bg-green-50 text-green-700 text-xs font-medium rounded-full">场景化</span>
              </div>
              <h3 className="text-lg font-medium text-onsurface mb-1">投资分析</h3>
              <p className="text-sm text-onsurface-variant mb-4">股票、基金、行业深度分析</p>
              <button className="flex items-center gap-1 text-primary-600 text-sm font-medium group-hover:gap-2 transition-all">
                开始分析
                <span className="material-icons-round text-sm">arrow_forward</span>
              </button>
            </div>

            {/* Coming Soon */}
            <div className="bg-surface-variant rounded-2xl p-6 border border-outline-variant opacity-60 cursor-not-allowed">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center">
                  <span className="material-icons-round text-gray-400 text-2xl">code</span>
                </div>
                <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs font-medium rounded-full">即将推出</span>
              </div>
              <h3 className="text-lg font-medium text-gray-500 mb-1">代码审查</h3>
              <p className="text-sm text-gray-400 mb-4">PR 自动化审查、安全扫描</p>
              <button disabled className="flex items-center gap-1 text-gray-400 text-sm font-medium cursor-not-allowed">
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
        className={`fixed bottom-8 right-8 w-14 h-14 bg-primary-600 text-white rounded-2xl shadow-lg hover:shadow-xl hover:scale-105 transition-all flex items-center justify-center ${
          !isOpenclawConnected ? 'opacity-50 pointer-events-none' : ''
        }`}
      >
        <span className="material-icons-round text-2xl">add</span>
      </button>
    </div>
  )
}

export default App