export interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'recruiter' | 'manager'
  avatar?: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface AuthResponse {
  user: User
  token: string
  refreshToken?: string
}

export type SSOProvider = 'microsoft' | 'google' | 'azure'
