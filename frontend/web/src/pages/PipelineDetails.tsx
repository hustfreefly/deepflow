import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Header from '../components/Header'

interface StageInfo {
  status: string
  stage: string
  data: Record<string, any>
  harness_self_assessment?: Record<string, any>
}

interface StagesResponse {
  session_id: string
  stages: Record<string, StageInfo>
  data: Record<string, any>
  stage_order: string[]
}

const stageLabels: Record<string, string> = {
  data_collection: '数据采集',
  planning: '规划制定',
  review_business: '商业评审',
  review_technical: '技术评审',
  review_risk: '风险评审',
  reviewers: '计划评审',
  research_expert_1: '研究专家 1',
  research_expert_2: '研究专家 2',
  research_expert_3: '研究专家 3',
  research: '并行研究',
  consolidator: '结果整合',
  audit: '质量审计',
  fix: '问题修复',
  fixer_expert: '修复专家',
  harness_final: '最终把关',
  summarizer: '报告生成',
}

const stageIcons: Record<string, string> = {
  data_collection: 'database',
  planning: 'edit_note',
  review_business: 'business',
  review_technical: 'engineering',
  review_risk: 'warning',
  reviewers: 'rate_review',
  research_expert_1: 'science',
  research_expert_2: 'science',
  research_expert_3: 'science',
  research: 'group',
  consolidator: 'merge_type',
  audit: 'verified',
  fix: 'build',
  fixer_expert: 'construction',
  harness_final: 'security',
  summarizer: 'summarize',
}

const PipelineDetails: React.FC = () => {
  const navigate = useNavigate()
  const { sessionId } = useParams<{ sessionId: string }>()
  
  const [stagesData, setStagesData] = useState<StagesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedStage, setExpandedStage] = useState<string | null>(null)
  
  useEffect(() => {
    if (!sessionId) return
    
    const fetchStages = async () => {
      try {
        const response = await fetch(`/api/v2/sessions/${sessionId}/stages`)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = await response.json()
        setStagesData(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    
    fetchStages()
  }, [sessionId])
  
  const toggleStage = (name: string) => {
    setExpandedStage(expandedStage === name ? null : name)
  }
  
  const renderJsonPreview = (data: any, maxDepth = 2): React.ReactNode => {
    if (data === null || data === undefined) return <span className="text-gray-400">null</span>
    if (typeof data === 'string') return <span className="text-green-700">"{data.length > 100 ? data.slice(0, 100) + '…' : data}"</span>
    if (typeof data === 'number') return <span className="text-blue-700">{data}</span>
    if (typeof data === 'boolean') return <span className="text-purple-700">{data.toString()}</span>
    if (Array.isArray(data)) {
      if (data.length === 0) return <span className="text-gray-400">[]</span>
      return (
        <div className="pl-4 border-l-2 border-gray-200">
          <span className="text-gray-500 text-xs">{data.length} 项</span>
          {data.slice(0, 3).map((item, i) => (
            <div key={i} className="mt-1">
              {renderJsonPreview(item, maxDepth - 1)}
            </div>
          ))}
          {data.length > 3 && <span className="text-gray-400 text-xs">... +{data.length - 3} more</span>}
        </div>
      )
    }
    if (typeof data === 'object') {
      const keys = Object.keys(data)
      if (keys.length === 0) return <span className="text-gray-400">{"{}"}</span>
      return (
        <div className="pl-4 border-l-2 border-gray-200">
          {keys.slice(0, 8).map(key => (
            <div key={key} className="py-0.5">
              <span className="text-gray-600 text-xs font-mono">{key}:</span>{' '}
              {renderJsonPreview(data[key], maxDepth - 1)}
            </div>
          ))}
          {keys.length > 8 && <span className="text-gray-400 text-xs">... +{keys.length - 8} more</span>}
        </div>
      )
    }
    return <span>{String(data)}</span>
  }
  
  return (
    <div className="min-h-screen bg-surface-variant">
      <Header openclawStatus="connected" apiStatus="ok" version="0.1.0" loading={false} />
      
      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          <button 
            onClick={() => navigate('/history')}
            className="flex items-center gap-1 text-primary-600 text-sm font-medium mb-4 hover:gap-2 transition-all"
          >
            <span className="material-icons-round text-sm">arrow_back</span>
            返回历史
          </button>
          <h1 className="text-2xl font-medium text-onsurface">管线执行详情</h1>
          <p className="text-onsurface-variant mt-1 font-mono text-sm">{sessionId}</p>
        </div>
        
        {loading && (
          <div className="bg-white rounded-2xl p-12 shadow-sm border border-outline-variant text-center">
            <span className="material-icons-round text-primary-600 text-4xl animate-spin">refresh</span>
            <p className="mt-4 text-onsurface-variant">加载管线数据...</p>
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
        
        {stagesData && (
          <>
            {/* View Report Button */}
            <div className="bg-white rounded-2xl p-4 mb-4 shadow-sm border border-outline-variant">
              <button
                onClick={() => navigate(`/report/${sessionId}`)}
                className="w-full flex items-center justify-between p-3 bg-primary-50 rounded-xl hover:bg-primary-100 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center">
                    <span className="material-icons-round text-white text-xl">description</span>
                  </div>
                  <div className="text-left">
                    <div className="text-sm font-medium text-onsurface">查看完整报告</div>
                    <div className="text-xs text-onsurface-variant">查看最终生成的完整方案文档</div>
                  </div>
                </div>
                <span className="material-icons-round text-primary-600 group-hover:translate-x-1 transition-transform">chevron_right</span>
              </button>
            </div>

            {/* Stage Timeline */}
            <div className="space-y-2">
              {stagesData.stage_order.map((stageName) => {
                const stage = stagesData.stages[stageName]
                if (!stage) return null
                
                const isExpanded = expandedStage === stageName
                const statusColor = stage.status === 'completed' ? 'border-green-200 bg-green-50' : 
                                   stage.status === 'running' ? 'border-primary-200 bg-primary-50' : 
                                   'border-gray-200 bg-gray-50'
                const iconColor = stage.status === 'completed' ? 'text-green-600' : 
                                 stage.status === 'running' ? 'text-primary-600 animate-spin' : 
                                 'text-gray-400'
                
                return (
                  <div key={stageName}>
                    {/* Stage Card */}
                    <div 
                      onClick={() => toggleStage(stageName)}
                      className={`rounded-xl border-2 p-4 cursor-pointer transition-all hover:shadow-md ${statusColor}`}
                    >
                      <div className="flex items-center gap-4">
                        {/* Stage Number */}
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-white shadow-sm`}>
                          {stage.status === 'completed' ? (
                            <span className="material-icons-round text-green-600 text-sm">check_circle</span>
                          ) : (
                            <span className={`material-icons-round text-sm ${iconColor}`}>
                              {stageIcons[stageName] || 'circle'}
                            </span>
                          )}
                        </div>
                        
                        {/* Stage Info */}
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <h3 className="text-sm font-medium text-onsurface">
                              {stageLabels[stageName] || stageName}
                            </h3>
                            <span className="text-xs text-onsurface-variant">
                              {stage.status === 'completed' ? '已完成' : stage.status}
                            </span>
                          </div>
                        </div>
                        
                        {/* Expand Icon */}
                        <span className={`material-icons-round text-sm transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                          expand_more
                        </span>
                      </div>
                    </div>
                    
                    {/* Expanded Content */}
                    {isExpanded && (
                      <div className="ml-6 mt-2 mb-3 bg-white rounded-xl p-4 border border-outline-variant">
                        {/* Data section */}
                        {stage.data && Object.keys(stage.data).length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-onsurface-variant mb-2 uppercase tracking-wide">输出数据</h4>
                            <div className="bg-surface-variant rounded-lg p-3 overflow-x-auto">
                              {renderJsonPreview(stage.data)}
                            </div>
                          </div>
                        )}
                        
                        {/* Harness Assessment */}
                        {stage.harness_self_assessment && (
                          <div className="mt-4">
                            <h4 className="text-xs font-medium text-onsurface-variant mb-2 uppercase tracking-wide">质量评估</h4>
                            <div className="flex gap-4 flex-wrap">
                              {Object.entries(stage.harness_self_assessment).map(([key, value]) => {
                                if (key.endsWith('_score') || typeof value === 'number') {
                                  const score = typeof value === 'number' ? value : 0
                                  const color = score >= 85 ? 'text-green-600' : score >= 70 ? 'text-yellow-600' : 'text-red-600'
                                  return (
                                    <div key={key} className="text-center">
                                      <div className={`text-lg font-bold ${color}`}>{score}</div>
                                      <div className="text-xs text-onsurface-variant">{key.replace('_score', '')}</div>
                                    </div>
                                  )
                                }
                                if (key === 'overall' && typeof value === 'string') {
                                  const colors: Record<string, string> = { green: 'text-green-600', yellow: 'text-yellow-600', red: 'text-red-600' }
                                  return (
                                    <div key={key} className="text-center">
                                      <div className={`text-lg font-bold ${colors[value] || 'text-gray-600'}`}>
                                        {value === 'green' ? '✅' : value === 'yellow' ? '⚠️' : '❌'} {value}
                                      </div>
                                      <div className="text-xs text-onsurface-variant">总体评估</div>
                                    </div>
                                  )
                                }
                                return null
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            
            {/* Data Files Section */}
            {stagesData.data && Object.keys(stagesData.data).length > 0 && (
              <div className="mt-6 bg-white rounded-2xl p-6 shadow-sm border border-outline-variant">
                <h2 className="text-lg font-medium text-onsurface mb-4 flex items-center gap-2">
                  <span className="material-icons-round text-onsurface-variant">folder</span>
                  数据文件
                </h2>
                <div className="space-y-2">
                  {Object.entries(stagesData.data).map(([name, data]) => (
                    <div key={name} className="flex items-center justify-between p-3 bg-surface-variant rounded-lg">
                      <div className="flex items-center gap-3">
                        <span className="material-icons-round text-primary-600">description</span>
                        <span className="text-sm font-medium text-onsurface">{name}.json</span>
                      </div>
                      <span className="text-xs text-onsurface-variant">
                        {typeof data === 'object' ? `${Object.keys(data).length} keys` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}

export default PipelineDetails
