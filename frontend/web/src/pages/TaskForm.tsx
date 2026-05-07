import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'

const TaskForm: React.FC = () => {
  const navigate = useNavigate()
  const pathParts = window.location.pathname.split('/')
  const domain = pathParts[pathParts.length - 1] || 'solution'
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Solution Pro form state
  const [topic, setTopic] = useState('')
  const [solutionType, setSolutionType] = useState('architecture')
  const [constraints, setConstraints] = useState('')
  const [stakeholders, setStakeholders] = useState('')
  const [sessionPrefix, setSessionPrefix] = useState('')
  
  // Investment form state
  const [code, setCode] = useState('688981.SH')
  const [name, setName] = useState('中芯国际')
  const [industry, setIndustry] = useState('半导体制造')
  const [analysisDepth, setAnalysisDepth] = useState('standard')
  
  const isSolution = domain === 'solution'
  const isInvestment = domain === 'investment'
  
  const handleSubmit = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const params = isSolution ? {
        domain: 'solution',
        topic,
        solution_type: solutionType,
        constraints: constraints.split('\n').filter(Boolean),
        stakeholders: stakeholders.split('\n').filter(Boolean),
        session_prefix: sessionPrefix,
      } : {
        domain: 'investment',
        code,
        name,
        industry,
        analysis_depth: analysisDepth,
        session_prefix: sessionPrefix,
      }
      
      const response = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to create task')
      }
      
      const data = await response.json()
      navigate(`/progress/${data.session_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="min-h-screen bg-surface-variant">
      <Header openclawStatus="connected" apiStatus="ok" version="0.1.0" loading={false} />
      
      <main className="max-w-3xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          <button 
            onClick={() => navigate('/')}
            className="flex items-center gap-1 text-primary-600 text-sm font-medium mb-4 hover:gap-2 transition-all"
          >
            <span className="material-icons-round text-sm">arrow_back</span>
            返回首页
          </button>
          <h1 className="text-2xl font-medium text-onsurface">
            {isSolution ? '新建方案设计任务' : '新建投资分析任务'}
          </h1>
          <p className="text-onsurface-variant mt-1">
            {isSolution ? '输入研究主题和约束条件' : '输入股票代码和公司信息'}
          </p>
        </div>
        
        {/* Form */}
        <div className="bg-white rounded-2xl p-8 shadow-sm border border-outline-variant">
          {isSolution && (
            <>
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  研究主题 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="例如：设计一个智能物流仓储系统升级方案"
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all"
                />
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  方案类型
                </label>
                <select
                  value={solutionType}
                  onChange={(e) => setSolutionType(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all bg-white"
                >
                  <option value="architecture">架构设计</option>
                  <option value="strategy">战略规划</option>
                  <option value="research">技术研究</option>
                </select>
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  约束条件（每行一个）
                </label>
                <textarea
                  value={constraints}
                  onChange={(e) => setConstraints(e.target.value)}
                  placeholder="预算500万&#10;周期6个月"
                  rows={3}
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all resize-none"
                />
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  干系人（每行一个）
                </label>
                <textarea
                  value={stakeholders}
                  onChange={(e) => setStakeholders(e.target.value)}
                  placeholder="技术团队&#10;财务总监"
                  rows={2}
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all resize-none"
                />
              </div>
            </>
          )}
          
          {isInvestment && (
            <>
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  股票代码 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="例如：688981.SH"
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all"
                />
                <p className="text-xs text-onsurface-variant mt-1">格式：代码.交易所（如 688981.SH）</p>
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  公司名称 <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：中芯国际"
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all"
                />
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  所属行业
                </label>
                <input
                  type="text"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  placeholder="例如：半导体制造"
                  className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all"
                />
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-onsurface mb-2">
                  分析深度
                </label>
                <div className="flex gap-3">
                  {['quick', 'standard', 'deep'].map((depth) => (
                    <button
                      key={depth}
                      onClick={() => setAnalysisDepth(depth)}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        analysisDepth === depth
                          ? 'bg-primary-50 text-primary-600 border-2 border-primary-200'
                          : 'bg-surface-variant text-onsurface-variant border-2 border-transparent hover:bg-outline'
                      }`}
                    >
                      {depth === 'quick' ? '快速' : depth === 'standard' ? '标准' : '深度'}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
          
          <div className="mb-6">
            <label className="block text-sm font-medium text-onsurface mb-2">
              会话前缀（可选）
            </label>
            <input
              type="text"
              value={sessionPrefix}
              onChange={(e) => setSessionPrefix(e.target.value)}
              placeholder="例如：smic-analysis"
              className="w-full px-4 py-3 rounded-xl border border-outline focus:border-primary-500 focus:ring-2 focus:ring-primary-100 outline-none transition-all"
            />
          </div>
          
          {error && (
            <div className="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-2">
              <span className="material-icons-round text-red-600 text-sm">error</span>
              <span className="text-sm text-red-700">{error}</span>
            </div>
          )}
          
          <div className="flex gap-3">
            <button
              onClick={() => navigate('/')}
              className="px-6 py-3 bg-surface-variant text-onsurface rounded-xl font-medium hover:bg-outline transition-colors border border-outline"
            >
              取消
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading || (isSolution ? !topic : !code || !name)}
              className="flex-1 px-6 py-3 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors disabled:bg-outline disabled:text-onsurface-variant disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="material-icons-round animate-spin">refresh</span>
                  启动中...
                </>
              ) : (
                <>
                  <span className="material-icons-round">rocket_launch</span>
                  启动分析
                </>
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

export default TaskForm