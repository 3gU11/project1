const INVENTORY_SYNC_EVENT = 'mobile-inventory-sync'

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let stopped = true
let currentToken = ''

export const isInventorySyncMessage = (message: unknown) => {
  const type = String((message as any)?.type || '')
  return type === 'INVENTORY_UPDATE' || type === 'WAREHOUSE_LAYOUT_UPDATE'
}

const connect = () => {
  if (stopped || !currentToken || typeof WebSocket === 'undefined') return
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  socket = new WebSocket(
    `${protocol}//${window.location.host}/api/v1/ws?token=${encodeURIComponent(currentToken)}`,
  )
  socket.addEventListener('message', (event) => {
    try {
      const message = JSON.parse(event.data)
      if (isInventorySyncMessage(message)) {
        window.dispatchEvent(new CustomEvent(INVENTORY_SYNC_EVENT, { detail: message }))
      }
    } catch {
      // Ignore malformed messages from unrelated global channels.
    }
  })
  socket.addEventListener('close', () => {
    socket = null
    if (!stopped) reconnectTimer = setTimeout(connect, 3000)
  })
  socket.addEventListener('error', () => socket?.close())
}

export const startInventorySync = (token: string) => {
  currentToken = token
  stopped = false
  connect()
}

export const stopInventorySync = () => {
  stopped = true
  currentToken = ''
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = null
  socket?.close()
  socket = null
}

export { INVENTORY_SYNC_EVENT }
