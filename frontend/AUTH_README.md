# Authentication System - Frontend

## 🔐 Implementation Overview

This authentication system implements **SSO (Single Sign-On)** with Microsoft Connect, along with traditional email/password authentication.

## 📁 Files Created

### Core Files

1. **`src/stores/authStore.ts`** - Zustand store for authentication state
2. **`src/routes/login.tsx`** - Login page with exact design from mockup
3. **`src/routes/sso-callback.tsx`** - SSO callback handler
4. **`src/components/ui/label.tsx`** - Label component (Radix UI)
5. **`src/components/shared/AuthGuard.tsx`** - Route protection component
6. **`src/hooks/useProtectedRoute.ts`** - Protected route hook
7. **`src/types/auth.ts`** - TypeScript type definitions

### Modified Files

- **`src/routes/__root.tsx`** - Updated to handle public/private routes
- **`src/index.css`** - Added custom animations

## 🚀 Features

### ✅ Implemented Features

- **Email/Password Login** - Traditional authentication
- **Microsoft SSO** - Single Sign-On with Microsoft Connect
- **Token Persistence** - Auth state persisted in localStorage
- **Protected Routes** - Automatic redirect to login for unauthenticated users
- **Loading States** - Proper loading indicators during auth
- **Error Handling** - User-friendly error messages
- **Responsive Design** - Mobile and desktop optimized
- **Animations** - Smooth transitions and hover effects

### 🎨 Design Features

- **Split Layout** - Form on left, branding on right
- **Gradient Background** - Smooth gray gradient with pattern overlay
- **Feature Cards** - Animated "AI Matching" and "Analytics" cards
- **Social Proof** - "500+ HR Managers" badge
- **Microsoft Branding** - Official Microsoft logo in SSO button

## 🔧 Usage

### 1. Accessing the Login Page

Navigate to `/login` in your application.

### 2. Login Methods

#### Email/Password
```typescript
// Automatic - handled by form submission
// Enter email and password, click "Sign In"
```

#### Microsoft SSO
```typescript
// Click "Microsoft Connect" button
// Redirects to: /api/auth/sso/microsoft
// Returns to: /sso-callback?token=...&user=...
```

### 3. Protecting Routes

#### Option A: Using AuthGuard Component
```typescript
import { AuthGuard } from '@/components/shared/AuthGuard'

function ProtectedPage() {
  return (
    <AuthGuard>
      <div>Protected Content</div>
    </AuthGuard>
  )
}
```

#### Option B: Using useProtectedRoute Hook
```typescript
import { useProtectedRoute } from '@/hooks/useProtectedRoute'

function ProtectedPage() {
  const { isAuthenticated, isLoading } = useProtectedRoute()
  
  if (isLoading) return <div>Loading...</div>
  
  return <div>Protected Content</div>
}
```

### 4. Accessing Auth State

```typescript
import { useAuthStore } from '@/stores/authStore'

function MyComponent() {
  const { user, isAuthenticated, logout } = useAuthStore()
  
  return (
    <div>
      {isAuthenticated && (
        <div>
          <p>Welcome, {user?.name}</p>
          <button onClick={logout}>Logout</button>
        </div>
      )}
    </div>
  )
}
```

## 🔌 Backend Integration (TODO)

The frontend is ready, but you need to implement these backend endpoints:

### Required Endpoints

#### 1. Email/Password Login
```python
POST /api/auth/login
Content-Type: application/json

Request:
{
  "email": "user@sofrecom.com",
  "password": "password123"
}

Response:
{
  "user": {
    "id": "uuid",
    "email": "user@sofrecom.com",
    "name": "John Doe",
    "role": "recruiter"
  },
  "token": "jwt_token_here"
}
```

#### 2. Microsoft SSO Redirect
```python
GET /api/auth/sso/microsoft
→ Redirects to Microsoft OAuth
```

#### 3. SSO Callback
```python
GET /api/auth/sso/callback
→ Processes OAuth callback
→ Redirects to: /sso-callback?token=...&user=...
```

#### 4. Get Current User
```python
GET /api/auth/me
Authorization: Bearer {token}

Response:
{
  "id": "uuid",
  "email": "user@sofrecom.com",
  "name": "John Doe",
  "role": "recruiter"
}
```

## 📦 Dependencies Installed

```json
{
  "zustand": "^4.x.x",
  "@radix-ui/react-label": "^2.x.x"
}
```

## 🎯 Public Routes

These routes are accessible without authentication:
- `/login`
- `/sso-callback`

All other routes require authentication and will redirect to `/login`.

## 🔄 Authentication Flow

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ├─────► /login (Login Page)
       │
       ├─────► Enter Credentials OR Click "Microsoft Connect"
       │
       ├─────► POST /api/auth/login OR GET /api/auth/sso/microsoft
       │
       ├─────► Receive Token + User Data
       │
       ├─────► Store in Zustand + localStorage
       │
       └─────► Navigate to / (Dashboard)
```

## 🎨 Design Specifications

- **Colors**: Gray scale with blue accents
- **Font**: Inter (already configured in project)
- **Border Radius**: 0.5rem (rounded-lg)
- **Shadows**: Subtle shadows on hover
- **Transitions**: 0.3s ease-out
- **Breakpoint**: lg (1024px) for split layout

## ⚡ Next Steps

1. **Implement Backend Endpoints** (see Backend Integration section)
2. **Add Forgot Password Flow** (optional)
3. **Add Google SSO** (optional)
4. **Add Remember Me** (optional)
5. **Add Multi-factor Authentication** (optional)

## 🐛 Testing

To test without backend:
1. Go to `/login`
2. Enter any email/password
3. It will fail (expected) - showing error message
4. Click "Microsoft Connect" - redirects to backend endpoint

To test with mock data:
```typescript
// In authStore.ts, temporarily replace login function:
login: async (email: string, password: string) => {
  set({ isLoading: true })
  
  // Mock delay
  await new Promise(resolve => setTimeout(resolve, 1000))
  
  // Mock success
  set({
    user: {
      id: '1',
      email,
      name: 'Test User',
      role: 'recruiter'
    },
    token: 'mock_token_123',
    isAuthenticated: true,
    isLoading: false,
  })
}
```

## 📝 Notes

- Token is stored in localStorage via Zustand persist
- Auto-logout on 401 responses (implemented in checkAuth)
- SSO callback uses URL query parameters for data transfer
- All animations are CSS-based for performance
- Design matches the provided mockup exactly

---

**Created by**: AI Assistant
**Date**: May 6, 2026
**Stack**: React + TypeScript + TanStack Router + Zustand + Tailwind CSS
