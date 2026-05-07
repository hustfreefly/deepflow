import { useNavigate } from 'react-router-dom'

interface HeaderProps {
  openclawStatus: string
  apiStatus: string
  version: string
  loading: boolean
}

const Header: React.FC<HeaderProps> = ({ openclawStatus, apiStatus, version, loading }) => {
  const navigate = useNavigate()
  
  const getOpenclawColor = () => {
    if (loading) return 'bg-gray-400'
    switch (openclawStatus) {
      case 'connected': return 'bg-green-500'
      case 'not_installed': return 'bg-yellow-500'
      default: return 'bg-red-500'
    }
  }

  const getOpenclawText = () => {
    if (loading) return '检测中'
    switch (openclawStatus) {
      case 'connected': return '已连接'
      case 'not_installed': return '未安装'
      default: return '异常'
    }
  }

  const getApiColor = () => {
    return apiStatus === 'ok' ? 'bg-green-500' : 'bg-red-500'
  }

  return (
    <header className="bg-white border-b border-outline-variant shadow-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Left: Logo + Title */}
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-primary-600 rounded-xl flex items-center justify-center shadow-md">
            <span className="material-icons-round text-white text-xl">psychology</span>
          </div>
          <div>
            <h1 className="text-xl font-medium text-onsurface tracking-tight">DeepFlow</h1>
            <p className="text-xs text-onsurface-variant leading-tight">多 Agent 分析管线</p>
          </div>
        </div>

        {/* Center: Navigation */}
        <nav className="hidden md:flex items-center gap-1">
          <button 
            onClick={() => navigate('/')}
            className="px-4 py-2 rounded-lg text-sm font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 transition-colors"
          >
            <span className="material-icons-round text-sm mr-1 align-text-bottom">dashboard</span>
            概览
          </button>
          <button 
            onClick={() => navigate('/history')}
            className="px-4 py-2 rounded-lg text-sm font-medium text-onsurface-variant hover:bg-surface-variant transition-colors"
          >
            <span className="material-icons-round text-sm mr-1 align-text-bottom">history</span>
            历史
          </button>
        </nav>

        {/* Right: Compact System Status + Actions */}
        <div className="flex items-center gap-3">
          {/* Compact System Status */}
          <div className="hidden lg:flex items-center gap-3 px-3 py-1.5 bg-surface-variant rounded-xl border border-outline">
            {/* OpenClaw */}
            <div className="flex items-center gap-1.5" title="OpenClaw">
              <div className={`w-1.5 h-1.5 rounded-full ${getOpenclawColor()} ${loading ? 'animate-pulse' : ''}`}></div>
              <span className="text-xs text-onsurface-variant">{getOpenclawText()}</span>
            </div>
            <div className="w-px h-3 bg-outline"></div>
            {/* API */}
            <div className="flex items-center gap-1.5" title="API">
              <div className={`w-1.5 h-1.5 rounded-full ${getApiColor()}`}></div>
              <span className="text-xs text-onsurface-variant">API</span>
            </div>
            <div className="w-px h-3 bg-outline"></div>
            {/* Version */}
            <div className="flex items-center gap-1" title="Version">
              <span className="material-icons-round text-xs text-onsurface-variant">new_releases</span>
              <span className="text-xs text-onsurface-variant">v{version}</span>
            </div>
          </div>

          {/* Settings Icon */}
          <button className="w-10 h-10 rounded-full hover:bg-surface-variant flex items-center justify-center transition-colors">
            <span className="material-icons-round text-onsurface-variant">settings</span>
          </button>

          {/* Avatar */}
          <div className="w-9 h-9 rounded-full bg-primary-100 flex items-center justify-center">
            <span className="material-icons-round text-primary-600 text-lg">person</span>
          </div>
        </div>
      </div>
    </header>
  )
}

export default Header