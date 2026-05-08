import { ref } from 'vue'
import { useUserStore } from '../store/user'

const listeners = new Map<string, Set<(data: any) => void>>()
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let shouldReconnect = false
let reconnectDelay = 3000
const MAX_RECONNECT_DELAY = 30000
let pingTimer: ReturnType<typeof setInterval> | null = null

export const wsConnected = ref(false)

function getSocketUrl() {
  const userStore = useUserStore()
  const token = userStore.token || ''
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v1/sandbox/ws?token=${encodeURIComponent(token)}`
}

function emit(event: string, data: any) {
  const handlers = listeners.get(event)
  if (!handlers) return
  handlers.forEach((handler) => {
    try { handler(data) } catch (e) { console.error('[WS] handler error:', e) }
  })
}

function scheduleReconnect() {
  if (!shouldReconnect || reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, reconnectDelay)
  reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_RECONNECT_DELAY)
}

function startPing() {
  stopPing()
  pingTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ event: 'ping' }))
    }
  }, 30000)
}

function stopPing() {
  if (pingTimer) {
    clearInterval(pingTimer)
    pingTimer = null
  }
}

export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }

  shouldReconnect = true
  const url = getSocketUrl()
  ws = new WebSocket(url)

  ws.addEventListener('open', () => {
    console.log('[WS] connected')
    wsConnected.value = true
    reconnectDelay = 3000
    startPing()
  })

  ws.addEventListener('message', (event) => {
    try {
      const message = JSON.parse(event.data)
      if (message?.event && message.event !== 'pong') {
        emit(message.event, message.data)
      }
    } catch (err) {
      // ignore non-JSON messages
    }
  })

  ws.addEventListener('error', (event) => {
    console.error('[WS] error:', event)
  })

  ws.addEventListener('close', (event) => {
    console.log('[WS] disconnected:', event.code)
    wsConnected.value = false
    ws = null
    stopPing()
    scheduleReconnect()
  })
}

export function disconnect() {
  shouldReconnect = false
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  stopPing()
  if (ws) {
    ws.close()
    ws = null
  }
  wsConnected.value = false
}

export function onEvent(event: string, handler: (data: any) => void): () => void {
  if (!listeners.has(event)) {
    listeners.set(event, new Set())
  }
  listeners.get(event)!.add(handler)
  return () => listeners.get(event)?.delete(handler)
}
