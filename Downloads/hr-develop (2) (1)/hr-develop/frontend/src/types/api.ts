export interface SystemStatus {
  status: string
  version?: string
  uptime?: number
}

export interface ApiError {
  detail: string
  status?: number
}
