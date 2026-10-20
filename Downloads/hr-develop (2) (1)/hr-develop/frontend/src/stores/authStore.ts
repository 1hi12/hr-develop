import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PublicClientApplication, AccountInfo, BrowserAuthError } from '@azure/msal-browser'
import { msalConfig, loginRequest, tokenRequest } from '@/lib/msalConfig'

// Initialize MSAL instance once
const msalInstance = new PublicClientApplication(msalConfig)
const authMode = (import.meta.env.VITE_AUTH_MODE ?? 'azure').toLowerCase()
const isMockAuth = authMode === 'mock'

// Initialize MSAL on module load
msalInstance.initialize().catch(err => {
  console.error('MSAL initialization failed:', err)
})

interface User {
  id: string
  email: string
  name: string
  role: string
}

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  
  // Actions
  login: (email: string, password: string) => Promise<void>
  loginWithSSO: (provider: 'microsoft') => Promise<void>
  logout: () => void
  setUser: (user: User, token: string) => void
  checkAuth: () => Promise<void>
}

function createMockUser(): User {
  return {
    id: 'mock-user-001',
    email: 'hiba1.hadded@sofrecom.com',
    name: 'Hiba Hadded',
    role: 'user',
  }
}

function createMockToken(): string {
  return `mock-token-${Date.now()}`
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email: string, password: string) => {
        set({ isLoading: true })
        try {
          const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          })

          if (!response.ok) {
            throw new Error('Login failed')
          }

          const data = await response.json()
          set({
            user: data.user,
            token: data.token,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error) {
          set({ isLoading: false })
          throw error
        }
      },

      loginWithSSO: async (provider: 'microsoft') => {
        // Prevent multiple clicks
        if (get().isLoading) {
          console.log('Login already in progress, ignoring')
          return
        }
        
        set({ isLoading: true })
        try {
          if (isMockAuth) {
            const user = createMockUser()
            const token = createMockToken()
            set({
              user,
              token,
              isAuthenticated: true,
              isLoading: false,
            })
            return
          }

          // Check if already authenticated
          const accounts = msalInstance.getAllAccounts()
          if (accounts.length > 0) {
            console.log('Already have account, using it:', accounts[0].username)
            
            // Get access token for existing account
            const tokenResponse = await msalInstance.acquireTokenSilent({
              ...tokenRequest,
              account: accounts[0],
            })
            
            const accessToken = tokenResponse.accessToken
            
            // Verify token with backend
            const verifyResponse = await fetch('http://localhost:8000/api/v1/auth/verify', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ access_token: accessToken }),
            })
            
            if (!verifyResponse.ok) {
              throw new Error('Token verification failed')
            }
            
            const verifyData = await verifyResponse.json()
            
            if (verifyData.valid && verifyData.user) {
              const user: User = {
                id: verifyData.user.oid,
                email: verifyData.user.email,
                name: verifyData.user.name || verifyData.user.email,
                role: 'user',
              }
              
              set({
                user,
                token: accessToken,
                isAuthenticated: true,
                isLoading: false,
              })
              return
            }
          }
          
          // No existing account, login with popup
          console.log('No existing account, opening login popup')
          const response = await msalInstance.loginPopup(loginRequest)
          
          if (response && response.account) {
            // Get access token
            const tokenResponse = await msalInstance.acquireTokenSilent({
              ...tokenRequest,
              account: response.account,
            })
            
            const accessToken = tokenResponse.accessToken
            
            // Verify token with backend
            const verifyResponse = await fetch('http://localhost:8000/api/v1/auth/verify', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ access_token: accessToken }),
            })
            
            if (!verifyResponse.ok) {
              throw new Error('Token verification failed')
            }
            
            const verifyData = await verifyResponse.json()
            
            if (verifyData.valid && verifyData.user) {
              // Create user object from Azure AD data
              const user: User = {
                id: verifyData.user.oid,
                email: verifyData.user.email,
                name: verifyData.user.name || verifyData.user.email,
                role: 'user',
              }
              
              set({
                user,
                token: accessToken,
                isAuthenticated: true,
                isLoading: false,
              })
            } else {
              throw new Error(verifyData.error || 'Authentication failed')
            }
          }
        } catch (error) {
          console.error('SSO login failed:', error)

          // Handle specific MSAL errors
          if (error instanceof BrowserAuthError) {
            const authErr = error as BrowserAuthError;
            if (authErr.errorCode === 'interaction_in_progress') {
              console.warn('Interaction already in progress, please wait')
            } else if (authErr.errorCode === 'user_cancelled') {
              console.log('User cancelled the login')
            }
          }
          
          set({ isLoading: false })
          throw error
        }
      },

      logout: async () => {
        if (isMockAuth) {
          set({
            user: null,
            token: null,
            isAuthenticated: false,
          })
          return
        }

        try {
          // Get the current MSAL account
          const accounts = msalInstance.getAllAccounts()
          if (accounts.length > 0) {
            // Logout from Azure AD
            await msalInstance.logoutPopup({
              account: accounts[0],
            })
          }
        } catch (error) {
          console.error('Azure AD logout failed:', error)
        }
        
        // Clear local state
        set({
          user: null,
          token: null,
          isAuthenticated: false,
        })
      },

      setUser: (user: User, token: string) => {
        set({
          user,
          token,
          isAuthenticated: true,
        })
      },

      checkAuth: async () => {
        const token = get().token
        if (!token) return

        if (isMockAuth && token.startsWith('mock-token-')) {
          set({
            user: createMockUser(),
            isAuthenticated: true,
          })
          return
        }

        try {
          const response = await fetch('/api/auth/me', {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          })

          if (response.ok) {
            const user = await response.json()
            set({ user, isAuthenticated: true })
          } else {
            get().logout()
          }
        } catch (error) {
          get().logout()
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
