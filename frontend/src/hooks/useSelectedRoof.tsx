import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

interface SelectedRoof {
  roofId: string | null
  setRoofId: (roofId: string | null) => void
}

const STORAGE_KEY = 'coolroof.selectedRoof'
const SelectedRoofContext = createContext<SelectedRoof>({
  roofId: null,
  setRoofId: () => undefined,
})

function storedRoof(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeRoof(roofId: string | null): void {
  try {
    if (roofId) sessionStorage.setItem(STORAGE_KEY, roofId)
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* Storage can be blocked; the selection then lasts until reload. */
  }
}

/** The roof last picked on the map or opened, so the navigation's escrow link follows it. */
export function SelectedRoofProvider({ children }: { children: ReactNode }): ReactNode {
  const [roofId, setRoof] = useState<string | null>(storedRoof)
  const setRoofId = (next: string | null): void => {
    storeRoof(next)
    setRoof(next)
  }
  return (
    <SelectedRoofContext.Provider value={{ roofId, setRoofId }}>
      {children}
    </SelectedRoofContext.Provider>
  )
}

export function useSelectedRoof(): SelectedRoof {
  return useContext(SelectedRoofContext)
}

/** Pages about one roof make it the selected roof. */
export function useRememberRoof(roofId: string): void {
  const { roofId: current, setRoofId } = useSelectedRoof()
  useEffect(() => {
    if (roofId && roofId !== current) setRoofId(roofId)
  }, [roofId, current, setRoofId])
}
