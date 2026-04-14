type MessageHandler = (data: string) => void
type StatusHandler = (connected: boolean) => void

const WS_URL =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000')
    : 'ws://localhost:8000'

class WebSocketClient {
  private ws: WebSocket | null = null
  private channel: string
  private handlers: MessageHandler[] = []
  private statusHandlers: StatusHandler[] = []
  private retryCount = 0
  private maxRetries = 10
  private baseDelay = 1000
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private intentionallyClosed = false

  constructor(channel: string) {
    this.channel = channel
  }

  connect(): void {
    if (typeof window === 'undefined') return
    this.intentionallyClosed = false
    this._open()
  }

  private _open(): void {
    try {
      this.ws = new WebSocket(`${WS_URL}/ws/${this.channel}`)

      this.ws.onopen = () => {
        this.retryCount = 0
        this.statusHandlers.forEach((h) => h(true))
      }

      this.ws.onmessage = (evt: MessageEvent<string>) => {
        this.handlers.forEach((h) => h(evt.data))
      }

      this.ws.onclose = () => {
        this.statusHandlers.forEach((h) => h(false))
        if (!this.intentionallyClosed) this._scheduleReconnect()
      }

      this.ws.onerror = () => {
        this.statusHandlers.forEach((h) => h(false))
      }
    } catch {
      this._scheduleReconnect()
    }
  }

  private _scheduleReconnect(): void {
    if (this.retryCount >= this.maxRetries) return
    const delay = Math.min(this.baseDelay * 2 ** this.retryCount, 30_000)
    this.retryCount++
    this.reconnectTimer = setTimeout(() => this._open(), delay)
  }

  disconnect(): void {
    this.intentionallyClosed = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler)
    }
  }

  onStatus(handler: StatusHandler): () => void {
    this.statusHandlers.push(handler)
    return () => {
      this.statusHandlers = this.statusHandlers.filter((h) => h !== handler)
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Singleton clients
export const transactionWS = new WebSocketClient('transactions')
export const metricsWS = new WebSocketClient('metrics')
