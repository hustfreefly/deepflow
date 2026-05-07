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
}

const HistoryPage: React.FC = () => {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('all')
  
  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await fetch('/api/sessions?limit=50')
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
  
  const filteredSessions = filter === 'all' 
    ? sessions 
    : sessions.filter(s => s.domain === filter)
  
  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  
  const domainLabels: Record<string, { label: string; color: string }> = {
    solution: { label: '方案设计', color: 'bg-primary-100 text-primary-700' },
    investment: { label: '投资分析', color: 'bg-green-100 text-green-700' },
    code_review: { label: '代码审查', color: 'bg-purple-100 text-purple-700' },
  }
  
  return (
    <div className="min-h-screen bg-surface-variant">
      <Header openclawStatus="connected" apiStatus="ok" version="0.1.0" loading={false} />
      
      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          <button 
            onClick={() => navigate('/')}
            className="flex items-center gap-1 text-primary-600 text-sm font-medium mb-4 hover:gap-2 transition-all"
          >
            <span className="material-icons-round text-sm">arrow_back</span>
            返回首页
          </button>
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-medium text-onsurface">历史记录</h1>
            
            {/* Filter */}
            <div className="flex gap-2">
              {[
                { value: 'all', label: '全部' },
                { value: 'solution', label: '方案设计' },
                { value: 'investment', label: '投资分析' },
              ].map((f) => (
                <button
                  key={f.value}
                  onClick={() => setFilter(f.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                    filter === f.value
                      ? 'bg-primary-50 text-primary-600'
                      : 'bg-surface-variant text-onsurface-variant hover:bg-outline'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        
        {loading && (
          <div className="bg-white rounded-2xl p-12 shadow-sm border border-outline-variant text-center">
            <span className="material-icons-round text-primary-600 text-4xl animate-spin">refresh</span>
            <p className="mt-4 text-onsurface-variant">加载中...</p>
          </div>
        )}
        
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-2xl p-6 flex items-start gap-3">
            <span className="material-icons-round text-red-600">error</span>
            <div>
              <p className="text-sm font-medium text-red-800">加载失败</p>
              <p className="text-xs text-red-700 mt-1">{error}</p>
            </div>
          </div>
        )}
        
        {!loading && !error && (
          <>
            {filteredSessions.length === 0 ? (
              <div className="bg-white rounded-2xl p-12 shadow-sm border border-outline-variant text-center">
                <span className="material-icons-round text-gray-300 text-6xl">history</span>
                <p className="mt-4 text-onsurface-variant">暂无历史记录</p>
                <button 
                  onClick={() => navigate('/')}
                  className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 transition-colors"
                >
                  开始第一个分析
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredSessions.map((session) => {
                  const domainInfo = domainLabels[session.domain] || { label: session.domain, color: 'bg-gray-100 text-gray-700' }
                  return (
                    <div 
                      key={session.session_id}
                      onClick={() => navigate(`/report/${session.session_id}`)}
                      className="bg-white rounded-2xl p-5 shadow-sm border border-outline-variant hover:shadow-md transition-all cursor-pointer"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className={`px-3 py-1 rounded-full text-xs font-medium ${domainInfo.color}`}>
                            {domainInfo.label}
                          </div>
                          <div>
                            <h3 className="font-medium text-onsurface">
                              {session.topic || session.code || session.session_id}
                            </h3>
                            <p className="text-xs text-onsurface-variant font-mono mt-0.5">
                              {session.session_id}
                            </p>
                          </div>
                        </div>
                        
                        <div className="flex items-center gap-4">
                          {session.quality_score !== undefined && (
                            <div className="flex items-center gap-1">
                              <span className="material-icons-round text-xs text-yellow-500">star</span>
                              <span className="text-sm font-medium text-onsurface">{session.quality_score}</span>
                            </div>
                          )}
                          <span className="text-xs text-onsurface-variant">{formatDate(session.created_at)}</span>
                          <span className="material-icons-round text-onsurface-variant">chevron_right</span>
                        </div>
                      </div>
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