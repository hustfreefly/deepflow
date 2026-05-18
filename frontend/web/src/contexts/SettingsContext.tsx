import React, { createContext, useContext, useState, useCallback } from 'react'
import SettingsDialog from '../components/SettingsDialog'

interface SettingsContextType {
  openSettings: () => void
}

const SettingsContext = createContext<SettingsContextType>({ openSettings: () => {} })

export const useSettings = () => useContext(SettingsContext)

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [show, setShow] = useState(false)
  const openSettings = useCallback(() => setShow(true), [])
  const closeSettings = useCallback(() => setShow(false), [])
  
  return (
    <SettingsContext.Provider value={{ openSettings }}>
      {children}
      {show && <SettingsDialog onClose={closeSettings} />}
    </SettingsContext.Provider>
  )
}
