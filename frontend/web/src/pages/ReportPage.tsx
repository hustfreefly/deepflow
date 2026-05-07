import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../components/Header'

interface ReportResponse {
  session_id: string
  content: string
  format: string
  length: number
}

const ReportPage: React.FC = () => {
  const navigate = useNavigate()
  const pathParts = window.location.pathname.split('/')
  const sessionId = pathParts[pathParts.length - 1]
  
  const [report, setReport] = useState<ReportResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  
  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await fetch(`/api/reports/${sessionId}`)
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = await response.json()
        setReport(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    
    fetchReport()
  }, [sessionId])
  
  const handleCopy = async () => {
    if (report?.content) {
      await navigator.clipboard.writeText(report.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }
  
  const handleDownload = () => {
    if (report?.content) {
      const blob = new Blob([report.content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${sessionId}_report.md`
      a.click()
      URL.revokeObjectURL(url)
    }
  }
  
  const handleFeishu = async () => {
    try {
      const response = await fetch(`/api/reports/${sessionId}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'feishu' }),
      })
      if (response.ok) {
        alert('报告已发送到飞书')
      } else {
        alert('发送失败')
      }
    } catch {
      alert('发送失败')
    }
  }
  
  // Simple markdown renderer
  const renderMarkdown = (content: string) => {
    return content
      .replace(/^### (.*$)/gim, '<h3 class="text-lg font-bold text-onsurface mt-6 mb-3">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold text-onsurface mt-8 mb-4">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold text-onsurface mt-10 mb-5">$1</h1>')
      .replace(/^\* (.*$)/gim, '<li class="ml-4 text-onsurface leading-relaxed">$1</li>')
      .replace(/^\- (.*$)/gim, '<li class="ml-4 text-onsurface leading-relaxed">$1</li>')
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="bg-surface-variant p-4 rounded-xl overflow-x-auto my-4"><code class="text-sm">$2</code></pre>')
      .replace(/`([^`]+)`/g, '<code class="bg-surface-variant px-1.5 py-0.5 rounded text-sm text-primary-700">$1</code>')
      .replace(/\n/g, '<br/>')
  }
  
  return (
    <div className="min-h-screen bg-surface-variant">
      <Header openclawStatus="connected" apiStatus="ok" version="0.1.0" loading={false} />
      
      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <button 
              onClick={() => navigate('/')}
              className="flex items-center gap-1 text-primary-600 text-sm font-medium mb-4 hover:gap-2 transition-all"
            >
              <span className="material-icons-round text-sm">arrow_back</span>
              返回首页
            </button>
            <h1 className="text-2xl font-medium text-onsurface">分析报告</h1>
            <p className="text-onsurface-variant mt-1 font-mono text-sm">{sessionId}</p>
          </div>
          
          {/* Actions */}
          <div className="flex gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-2 px-4 py-2 bg-surface-variant text-onsurface rounded-xl text-sm font-medium hover:bg-outline transition-colors border border-outline"
            >
              <span className="material-icons-round text-sm">{copied ? 'check' : 'content_copy'}</span>
              {copied ? '已复制' : '复制'}
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 px-4 py-2 bg-surface-variant text-onsurface rounded-xl text-sm font-medium hover:bg-outline transition-colors border border-outline"
            >
              <span className="material-icons-round text-sm">download</span>
              下载
            </button>
            <button
              onClick={handleFeishu}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-xl text-sm font-medium hover:bg-primary-700 transition-colors"
            >
              <span className="material-icons-round text-sm">send</span>
              飞书
            </button>
          </div>
        </div>
        
        {loading && (
          <div className="bg-white rounded-2xl p-12 shadow-sm border border-outline-variant text-center">
            <span className="material-icons-round text-primary-600 text-4xl animate-spin">refresh</span>
            <p className="mt-4 text-onsurface-variant">加载报告中...</p>
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
        
        {report && (
          <div className="bg-white rounded-2xl p-8 shadow-sm border border-outline-variant">
            <div 
              className="prose prose-sm max-w-none"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(report.content) }}
            />
          </div>
        )}
      </main>
    </div>
  )
}

export default ReportPage