import React, { useState, useCallback, useRef } from 'react'

export interface ExtractedSpec {
  topic: string
  solution_type: 'architecture' | 'business' | 'technical' | null
  constraints: string[]
  stakeholders: string[]
  confidence: number
  extracted_text: string
}

type UploadState = 'idle' | 'uploading' | 'processing' | 'success' | 'error'

interface SpecUploadProps {
  onExtracted: (spec: ExtractedSpec) => void
  onError?: (error: string) => void
  disabled?: boolean
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:17789'

const SpecUpload: React.FC<SpecUploadProps> = ({
  onExtracted,
  onError,
  disabled = false,
}) => {
  const [state, setState] = useState<UploadState>('idle')
  const [errorMsg, setErrorMsg] = useState<string>('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback(
    async (file: File) => {
      // Validate extension
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      if (!['.md', '.txt'].includes(ext)) {
        const msg = `不支持的文件格式: ${ext}。支持 .md 和 .txt`
        setErrorMsg(msg)
        setState('error')
        onError?.(msg)
        return
      }

      // Validate size (10MB)
      if (file.size > 10 * 1024 * 1024) {
        const msg = `文件过大 (${(file.size / 1024 / 1024).toFixed(1)}MB)，最大 10MB`
        setErrorMsg(msg)
        setState('error')
        onError?.(msg)
        return
      }

      setState('uploading')
      setErrorMsg('')

      const formData = new FormData()
      formData.append('file', file)

      try {
        const response = await fetch(`${API_BASE_URL}/api/v2/upload`, {
          method: 'POST',
          body: formData,
        })

        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: '上传失败' }))
          throw new Error(err.detail || `HTTP ${response.status}`)
        }

        const data: ExtractedSpec = await response.json()

        if (data.confidence === 0 && !data.topic) {
          // LLM extraction failed, but we have the text
          setState('error')
          const msg = '自动提取失败，请手动填写'
          setErrorMsg(msg)
          // Still pass the extracted text so user can work with it
          onExtracted(data)
          return
        }

        setState('success')
        onExtracted(data)
      } catch (err) {
        const msg = err instanceof Error ? err.message : '上传失败'
        setErrorMsg(msg)
        setState('error')
        onError?.(msg)
      }
    },
    [onExtracted, onError],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      if (disabled) return
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile, disabled],
  )

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) handleFile(file)
      // Reset input so same file can be re-uploaded
      if (inputRef.current) inputRef.current.value = ''
    },
    [handleFile],
  )

  const handleBrowse = () => {
    if (!disabled) inputRef.current?.click()
  }

  const handleReset = () => {
    setState('idle')
    setErrorMsg('')
  }

  return (
    <div className="bg-white rounded-2xl border border-outline-variant overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 bg-surface-variant border-b border-outline-variant flex items-center gap-3">
        <span className="material-icons-round text-primary-600">upload_file</span>
        <div>
          <h3 className="text-sm font-medium text-onsurface">上传需求文档</h3>
          <p className="text-xs text-onsurface-variant">
            支持 .md / .txt 文件，最大 10MB
          </p>
        </div>
      </div>

      {/* Drop Zone */}
      {state === 'idle' && (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            if (!disabled) setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={handleBrowse}
          className={`m-4 border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
            dragging
              ? 'border-primary-400 bg-primary-50'
              : 'border-outline-variant hover:border-primary-300 hover:bg-primary-50/50'
          }`}
        >
          <span className="material-icons-round text-4xl text-onsurface-variant mb-2 block">
            cloud_upload
          </span>
          <p className="text-sm text-onsurface font-medium">
            拖拽文件到此处，或点击浏览
          </p>
          <p className="text-xs text-onsurface-variant mt-1">
            .md / .txt 文件
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".md,.txt"
            onChange={handleInputChange}
            className="hidden"
            disabled={disabled}
          />
        </div>
      )}

      {/* Uploading */}
      {state === 'uploading' && (
        <div className="m-4 p-8 text-center">
          <span className="material-icons-round text-4xl text-primary-500 animate-spin mb-2 block">
            progress_activity
          </span>
          <p className="text-sm text-onsurface font-medium">正在分析文档...</p>
          <p className="text-xs text-onsurface-variant mt-1">
            AI 正在提取需求信息，请稍候
          </p>
        </div>
      )}

      {/* Success */}
      {state === 'success' && (
        <div className="m-4 p-4 bg-green-50 border border-green-200 rounded-xl flex items-start gap-3">
          <span className="material-icons-round text-green-600 mt-0.5">check_circle</span>
          <div className="flex-1">
            <p className="text-sm font-medium text-green-800">文档分析完成</p>
            <p className="text-xs text-green-700 mt-1">
              已自动提取需求信息，请在下方确认后提交
            </p>
          </div>
          <button
            onClick={handleReset}
            className="text-xs text-green-700 hover:text-green-900 font-medium px-2 py-1 rounded hover:bg-green-100"
          >
            重新上传
          </button>
        </div>
      )}

      {/* Error */}
      {state === 'error' && errorMsg && (
        <div className="m-4 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <span className="material-icons-round text-red-600 mt-0.5">error</span>
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800">上传失败</p>
            <p className="text-xs text-red-700 mt-1">{errorMsg}</p>
          </div>
          <button
            onClick={handleReset}
            className="text-xs text-red-700 hover:text-red-900 font-medium px-2 py-1 rounded hover:bg-red-100"
          >
            重试
          </button>
        </div>
      )}
    </div>
  )
}

export default SpecUpload
