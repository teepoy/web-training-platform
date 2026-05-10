export type ActivationMode = 'open' | 'select'

export interface ActivationEvent {
  ctrlKey: boolean
  metaKey: boolean
}

export interface ActivationCallbacks {
  onOpen: (id: string) => void
  onSelect: (id: string, multi: boolean) => void
}

export function handleBrowserActivation(
  mode: ActivationMode,
  id: string,
  event: ActivationEvent,
  callbacks: ActivationCallbacks,
): void {
  if (mode === 'open') {
    callbacks.onOpen(id)
  } else {
    callbacks.onSelect(id, event.ctrlKey || event.metaKey)
  }
}
