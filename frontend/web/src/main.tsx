import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App'
import TaskForm from './pages/TaskForm'
import ProgressPage from './pages/ProgressPage'
import ReportPage from './pages/ReportPage'
import HistoryPage from './pages/HistoryPage'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/task/:domain" element={<TaskForm />} />
        <Route path="/progress/:sessionId" element={<ProgressPage />} />
        <Route path="/report/:sessionId" element={<ReportPage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
