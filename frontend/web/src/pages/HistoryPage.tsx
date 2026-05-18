import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'

interface Session {
  session_id: string
  domain: string
  status: string
  created_at: number
  quality_score?: number
  topic?: string
  code?: string
  progress?: number
}

const HistoryPage: React.FC = () => {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  
  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('/api/v2/sessions?limit=50')
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = await response.json()
        setSessions(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    
    fetchSessions()
  }, [])
  
  const filteredSessions = sessions.filter(s => {
    if (filter !== 'all' && s.domain !== filter) return false
    if (statusFilter !== 'all' && s.status !== statusFilter) return false
    return true
  })
  
  // 智能时间格式化：今天、昨天、具体日期
  const formatDate = (timestamp: number) => {
    if (!timestamp) return '-'
    const date = new Date(timestamp * 1000)
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
    const dateWithoutTime = new Date(date.getFullYear(), date.getMonth(), date.getDate())
    
    const timeStr = date.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    })
    
    if (dateWithoutTime.getTime() === today.getTime()) {
      return `今天 ${timeStr}`
    } else if (dateWithoutTime.getTime() === yesterday.getTime()) {
      return `昨天 ${timeStr}`
    } else {
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    }
  }
  
  const truncate = (text: string, maxLen: number = 50) => {
    if (!text) return ''
    return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
  }
  
  // 状态配置：颜色、图标、标签
  const statusConfig: Record<string, { color: string; icon: string; label: string }> = {
    completed: { color: 'bg-green-100 text-green-700 border-green-200', icon: 'check_circle', label: '已完成' },
    running: { color: 'bg-primary-50 text-primary-600 border-primary-200', icon: 'play_circle', label: '执行中' },
    failed: { color: 'bg-red-50 text-red-600 border-red-200', icon: 'error', label: '失败' },
    pending: { color: 'bg-amber-50 text-amber-600 border-amber-200', icon: 'schedule', label: '排队中' },
    waiting_agent: { color: 'bg-amber-50 text-amber-600 border-amber-200', icon: 'hourglass_empty', label: '等待中' },
  }
  
  // 领域配置
  const domainConfig: Record<string, { icon: string; label: string; gradient: string }> = {
    solution: { 
      icon: 'architecture', 
      label: 'Solution Pro',
      gradient: 'from-primary-50 to-primary-100'
    },
    investment: { 
      icon: 'trending_up', 
      label: 'Investment',
      gradient: 'from-green-50 to-emerald-100'
    },
  }
  
  // 计算统计信息
  const stats = {
    total: sessions.length,
    completed: sessions.filter(s => s.status === 'completed').length,
    running: sessions.filter(s => s.status === 'running').length,
    failed: sessions.filter(s => s.status === 'failed').length,
  }
  
  return (
    <div className="min-h-screen bg-surface-variant">
      <Header openclawStatus="connected" apiStatus="ok" version="0.1.0" loading={false} />
      
      <main className="max-w-5xl mx-auto px-6 py-6">
        {/* Header */}
        <div className="mb-6">
          <button 
            onClick={() => navigate('/')}
            className="flex items-center gap-1.5 text-onsurface-variant text-sm font-medium mb-4 
                       hover:text-primary-600 transition-colors group"
          >
            <span className="material-icons-round text-base group-hover:-translate-x-0.5 transition-transform">
              arrow_back
            </span>
            返回首页
          </button>
          
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-onsurface">历史记录</h1>
              <p className="text-sm text-onsurface-variant mt-1">
                共 {stats.total} 个任务 · {stats.completed} 个已完成 · {stats.running} 个执行中
              </p>
            </div>
          </div>
        </div>
        
        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-5">
          {/* 领域筛选 */}
          <div className="flex gap-1.5 bg-white rounded-xl p-1.5 border border-outline-variant shadow-sm">
            {[
              { value: 'all', label: '全部', icon: 'all_inclusive' },
              { value: 'solution', label: 'Solution Pro', icon: 'architecture' },
              { value: 'investment', label: 'Investment', icon: 'trending_up' },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium 
                           transition-all duration-200 ${
                  filter === f.value
                    ? 'bg-primary-50 text-primary-700 shadow-sm'
                    : 'text-onsurface-variant hover:bg-surface-variant hover:text-onsurface'
                }`}
              >
                <span className="material-icons-round text-base">{f.icon}</span>
                {f.label}
              </button>
            ))}
          </div>
          
          {/* 状态筛选 */}
          <div className="flex gap-1.5 bg-white rounded-xl p-1.5 border border-outline-variant shadow-sm">
            {[
              { value: 'all', label: '全部状态' },
              { value: 'completed', label: '已完成', color: 'text-green-600' },
              { value: 'running', label: '执行中', color: 'text-primary-600' },
              { value: 'failed', label: '失败', color: 'text-red-600' },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  statusFilter === f.value
                    ? 'bg-primary-50 text-primary-700 shadow-sm'
                    : 'text-onsurface-variant hover:bg-surface-variant hover:text-onsurface'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        
        {/* Loading State */}
        {loading && (
          <div className="bg-white rounded-2xl p-16 shadow-sm border border-outline-variant">
            <div className="flex flex-col items-center">
              <div className="relative">
                <div className="w-12 h-12 rounded-full border-4 border-primary-100 border-t-primary-600 animate-spin" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="material-icons-round text-primary-600 text-sm">refresh</span>
                </div>
              </div>
              <p className="mt-5 text-onsurface font-medium">加载中</p>
              <p className="text-sm text-onsurface-variant mt-1">正在获取历史记录...</p>
            </div>
          </div>
        )}
        
        {/* Error State */}
        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-2xl p-6">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <span className="material-icons-round text-red-600">error_outline</span>
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-red-800">加载失败</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
                <button 
                  onClick={() => window.location.reload()}
                  className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium 
                           hover:bg-red-700 transition-colors inline-flex items-center gap-1.5"
                >
                  <span className="material-icons-round text-sm">refresh</span>
                  重试
                </button>
              </div>
            </div>
          </div>
        )}
        
        {/* Content */}
        {!loading && !error && (
          <>
            {filteredSessions.length === 0 ? (
              /* Empty State */
              <div className="bg-white rounded-2xl p-16 shadow-sm border border-outline-variant text-center">
                <div className="w-20 h-20 rounded-full bg-surface-variant flex items-center justify-center mx-auto mb-5">
                  <span className="material-icons-round text-onsurface-variant text-4xl">history</span>
                </div>
                <h3 className="text-lg font-semibold text-onsurface mb-2">
                  暂无历史记录
                </h3>
                <p className="text-sm text-onsurface-variant mb-6 max-w-sm mx-auto">
                  {sessions.length === 0 
                    ? '还没有创建过任何任务，开始你的第一次分析吧' 
                    : '当前筛选条件下没有匹配的任务，尝试调整筛选条件'}
                </p>
                <div className="flex gap-3 justify-center">
                  {sessions.length === 0 ? (
                    <button 
                      onClick={() => navigate('/')}
                      className="px-5 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium 
                               hover:bg-primary-700 transition-all shadow-sm hover:shadow-md 
                               inline-flex items-center gap-2"
                    >
                      <span className="material-icons-round text-sm">add</span>
                      创建第一个任务
                    </button>
                  ) : (
                    <>
                      <button 
                        onClick={() => { setFilter('all'); setStatusFilter('all'); }}
                        className="px-5 py-2.5 bg-primary-600 text-white rounded-xl text-sm font-medium 
                                 hover:bg-primary-700 transition-all shadow-sm hover:shadow-md"
                      >
                        清除筛选
                      </button>
                      <button 
                        onClick={() => navigate('/')}
                        className="px-5 py-2.5 border border-outline-variant text-onsurface rounded-xl 
                                 text-sm font-medium hover:bg-surface-variant transition-all"
                      >
                        创建新任务
                      </button>
                    </>
                  )}
                </div>
              </div>
            ) : (
              /* Session List */
              <div className="space-y-3">
                {filteredSessions.map((session) => {
                  const status = statusConfig[session.status] || { 
                    color: 'bg-gray-100 text-gray-700 border-gray-200', 
                    icon: 'help', 
                    label: session.status 
                  }
                  const domain = domainConfig[session.domain] || { 
                    icon: 'folder', 
                    label: session.domain,
                    gradient: 'from-gray-50 to-gray-100'
                  }
                  
                  return (
                    <div 
                      key={session.session_id}
                      onClick={() => {
                        if (session.status === 'completed' || session.status === 'running') {
                          navigate(`/pipeline/${session.session_id}`)
                        } else if (session.status === 'failed') {
                          navigate(`/progress/${session.session_id}`)
                        }
                      }}
                      className="group bg-white rounded-xl p-4 shadow-sm hover:shadow-lg hover:-translate-y-0.5 
                               transition-all duration-200 cursor-pointer"
                    >
                      <div className="flex items-center gap-4">
                        {/* Domain Icon */}
                        <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0
                                      bg-gradient-to-br ${domain.gradient} border border-outline-variant`}>
                          <span className={`material-icons-round text-xl ${
                            session.domain === 'solution' ? 'text-primary-600' : 'text-green-600'
                          }`}>
                            {domain.icon}
                          </span>
                        </div>
                        
                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 min-w-0">
                            <h3 className="text-sm font-semibold text-onsurface truncate">
                              {truncate(session.topic || session.code || '未命名任务', 55)}
                            </h3>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-onsurface-variant">
                            <span className="font-mono bg-surface-variant px-1.5 py-0.5 rounded">
                              {session.session_id.slice(0, 8)}...
                            </span>
                            <span>·</span>
                            <span>{domain.label}</span>
                            {session.quality_score !== undefined && session.quality_score > 0 && (
                              <>
                                <span>·</span>
                                <span className="flex items-center gap-0.5 text-amber-600">
                                  <span className="material-icons-round text-xs">star</span>
                                  {session.quality_score.toFixed(1)}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        
                        {/* Status & Time */}
                        <div className="flex items-center gap-3 flex-shrink-0">
                          {/* Status Badge */}
                          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full 
                                         text-xs font-medium border ${status.color}`}>
                            <span className="material-icons-round text-xs">{status.icon}</span>
                            {status.label}
                          </span>
                          
                          {/* Time */}
                          <span className="text-xs text-onsurface-variant whitespace-nowrap min-w-[80px] text-right">
                            {formatDate(session.created_at)}
                          </span>
                          
                          {/* Arrow */}
                          <span className="material-icons-round text-lg text-onsurface-variant 
                                         group-hover:text-primary-600 group-hover:translate-x-0.5 
                                         transition-all duration-200">
                            chevron_right
                          </span>
                        </div>
                      </div>
                      
                      {/* Progress bar for running tasks */}
                      {session.status === 'running' && session.progress !== undefined && (
                        <div className="mt-3 pt-3 border-t border-outline-variant">
                          <div className="flex items-center gap-3">
                            <div className="flex-1 h-1.5 bg-surface-variant rounded-full overflow-hidden">
                              <div 
                                className="h-full bg-primary-600 rounded-full transition-all duration-500"
                                style={{ width: `${Math.min(session.progress * 100, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs font-medium text-primary-600 min-w-[40px] text-right">
                              {Math.round(session.progress * 100)}%
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default HistoryPage
