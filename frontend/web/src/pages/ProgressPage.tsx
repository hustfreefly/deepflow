import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Header from '../components/Header'

interface Stage {
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  duration: number
  workers?: { completed: number; total: number }
}

interface StatusResponse {
  session_id: string
  status: string
  current_stage: string
  progress: number
  stages: Stage[]
  quality_score: number | null
  harness_scores: {
    completeness?: number
    necessity?: number
    target_alignment?: number
  }
  elapsed: number
}

const ProgressPage: React.FC = () => {
  const navigate = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  useEffect(() => {
    if (!sessionId) return
    
    const checkStatus = async () => {
      try {
        const response = await fetch(`/api/status/${sessionId}`)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = await response.json()
        setStatus(data)
        
        // If completed, redirect to report after 3 seconds
        if (data.status === 'completed') {
          setTimeout(() => navigate(`/report/${sessionId}`), 3000)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    
    checkStatus()
    const interval = setInterval(checkStatus, 3000)
    return () => clearInterval(interval)
  }, [sessionId, navigate])
  
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}分${secs}秒`
  }
  
  const stageNames: Record<string, string> = {
    data_collection: '数据采集',
    planning: '规划制定',
    reviewers: '计划评审',
    researchers: '并行研究',
    consolidator: '结果整合',
    auditors: '质量审计',
    fixer: '问题修复',
    harness_final: '最终把关',
    summarizer: '报告生成',
  }
  
  const stageIcons: Record<string, string> = {
    data_collection: 'database',
    planning: 'edit_note',
    reviewers: 'rate_review',
    researchers: 'group',
    consolidator: 'merge_type',
    auditors: 'verified',
    fixer: 'build',
    harness_final: 'security',
    summarizer: 'summarize',
  }
  
  return (
    <div className="min-h-screen bg-surface-variant">
      <Header openclawStatus="connected" apiStatus="ok" version="0.1.0" loading={false} />
      
      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          <button 
            onClick={() => navigate('/')}
            className="flex items-center gap-1 text-primary-600 text-sm font-medium mb-4 hover:gap-2 transition-all"
          >
            <span className="material-icons-round text-sm">arrow_back</span>
            返回首页
          </button>
          <h1 className="text-2xl font-medium text-onsurface">分析进度</h1>
          <p className="text-onsurface-variant mt-1 font-mono text-sm">{sessionId}</p>
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
        
        {status && (
          <>
            {/* Overall Progress */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant mb-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-medium text-onsurface">总体进度</h2>
                  <p className="text-sm text-onsurface-variant">
                    已用时 {formatTime(status.elapsed)}
                  </p>
                </div>
                <div className="text-right">
                  <span className={`text-3xl font-bold ${
                    status.status === 'completed' ? 'text-green-600' : 
                    status.status === 'queued' ? 'text-yellow-600' : 'text-primary-600'
                  }`}>
                    {status.status === 'queued' ? '排队中' : 
                     status.status === 'completed' ? '已完成' :
                     `${Math.round(status.progress * 100)}%`}
                  </span>
                </div>
              </div>
              
              {/* Progress Bar */}
              <div className="w-full h-3 bg-surface-variant rounded-full overflow-hidden">
                <div 
                  className={`h-full rounded-full transition-all duration-500 ${
                    status.status === 'queued' ? 'bg-yellow-400' : 'bg-primary-500'
                  }`}
                  style={{ width: `${status.progress * 100}%` }}
                ></div>
              </div>
              
              {status.status === 'queued' && (
                <p className="text-sm text-yellow-600 mt-3 flex items-center gap-1">
                  <span className="material-icons-round text-sm">schedule</span>
                  任务已排队，等待 Agent 执行...
                </p>
              )}
            </div>
            
            {/* Pipeline Stages */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant mb-6">
              <h2 className="text-lg font-medium text-onsurface mb-4 flex items-center gap-2">
                <span className="material-icons-round text-onsurface-variant">view_timeline</span>
                管线阶段
              </h2>
              
              <div className="space-y-3">
                {status.stages.map((stage) => (
                  <div 
                    key={stage.name}
                    className={`flex items-center gap-4 p-4 rounded-xl transition-all ${
                      stage.status === 'running' 
                        ? 'bg-primary-50 border border-primary-100' 
                        : stage.status === 'completed'
                        ? 'bg-green-50 border border-green-100'
                        : 'bg-surface border border-outline'
                    }`}
                  >
                    {/* Stage Number / Icon */}
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                      stage.status === 'running'
                        ? 'bg-primary-100'
                        : stage.status === 'completed'
                        ? 'bg-green-100'
                        : 'bg-gray-100'
                    }`}>
                      {stage.status === 'completed' ? (
                        <span className="material-icons-round text-green-600">check_circle</span>
                      ) : stage.status === 'running' ? (
                        <span className="material-icons-round text-primary-600 animate-spin">refresh</span>
                      ) : (
                        <span className="material-icons-round text-gray-400">{stageIcons[stage.name] || 'circle'}</span>
                      )}
                    </div>
                    
                    {/* Stage Info */}
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <h3 className={`font-medium ${
                          stage.status === 'pending' ? 'text-gray-400' : 'text-onsurface'
                        }`}>
                          {stageNames[stage.name] || stage.name}
                        </h3>
                        <span className="text-xs text-onsurface-variant">
                          {stage.status === 'completed' ? `${stage.duration}秒` : ''}
                        </span>
                      </div>
                      
                      {/* Worker Progress */}
                      {stage.workers && stage.status === 'running' && (
                        <div className="mt-2">
                          <div className="flex items-center gap-2 text-xs text-onsurface-variant mb-1">
                            <span>Worker 进度</span>
                            <span>{stage.workers.completed}/{stage.workers.total}</span>
                          </div>
                          <div className="w-full h-1.5 bg-surface-variant rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-primary-400 rounded-full transition-all"
                              style={{ width: `${(stage.workers.completed / stage.workers.total) * 100}%` }}
                            ></div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            {/* Quality Scores */}
            {status.harness_scores && Object.keys(status.harness_scores).length > 0 && (
              <div className="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant mb-6">
                <h2 className="text-lg font-medium text-onsurface mb-4 flex items-center gap-2">
                  <span className="material-icons-round text-onsurface-variant">shield</span>
                  质量门控
                </h2>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {status.harness_scores.completeness !== undefined && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-onsurface-variant">完整性</span>
                        <span className="text-sm font-medium text-onsurface">{status.harness_scores.completeness}/100</span>
                      </div>
                      <div className="w-full h-2 bg-surface-variant rounded-full overflow-hidden">
                        <div 
                          className="h-full rounded-full transition-all"
                          style={{ 
                            width: `${status.harness_scores.completeness}%`,
                            backgroundColor: status.harness_scores.completeness >= 80 ? '#22c55e' : status.harness_scores.completeness >= 60 ? '#eab308' : '#ef4444'
                          }}
                        ></div>
                      </div>
                    </div>
                  )}
                  
                  {status.harness_scores.necessity !== undefined && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-onsurface-variant">必要性</span>
                        <span className="text-sm font-medium text-onsurface">{status.harness_scores.necessity}/100</span>
                      </div>
                      <div className="w-full h-2 bg-surface-variant rounded-full overflow-hidden">
                        <div 
                          className="h-full rounded-full transition-all"
                          style={{ 
                            width: `${status.harness_scores.necessity}%`,
                            backgroundColor: status.harness_scores.necessity >= 80 ? '#22c55e' : status.harness_scores.necessity >= 60 ? '#eab308' : '#ef4444'
                          }}
                        ></div>
                      </div>
                    </div>
                  )}
                  
                  {status.harness_scores.target_alignment !== undefined && (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-onsurface-variant">目标一致性</span>
                        <span className="text-sm font-medium text-onsurface">{status.harness_scores.target_alignment}/100</span>
                      </div>
                      <div className="w-full h-2 bg-surface-variant rounded-full overflow-hidden">
                        <div 
                          className="h-full rounded-full transition-all"
                          style={{ 
                            width: `${status.harness_scores.target_alignment}%`,
                            backgroundColor: status.harness_scores.target_alignment >= 80 ? '#22c55e' : status.harness_scores.target_alignment >= 60 ? '#eab308' : '#ef4444'
                          }}
                        ></div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {/* Completion Banner */}
            {status.status === 'completed' && (
              <div className="bg-green-50 border border-green-200 rounded-2xl p-6 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="material-icons-round text-green-600 text-2xl">check_circle</span>
                  <div>
                    <p className="font-medium text-green-800">分析完成！</p>
                    <p className="text-sm text-green-700">即将跳转到报告页面...</p>
                  </div>
                </div>
                <button 
                  onClick={() => navigate(`/report/${sessionId}`)}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition-colors"
                >
                  查看报告
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default ProgressPage