import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import {
  getCurrentUser,
  signIn,
  signOut,
  fetchUserAttributes,
  fetchAuthSession
} from 'aws-amplify/auth'
import { authService } from '../services/authService'
import type { AuthState, User } from '../types'

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<unknown>
  confirmRegistration: (email: string, code: string) => Promise<void>
  resendVerificationCode: (email: string) => Promise<void>
  forgotPassword: (email: string) => Promise<void>
  resetPassword: (email: string, code: string, newPassword: string) => Promise<void>
  logout: () => Promise<void>
  refreshAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    error: null
  })

  const checkAuthStatus = useCallback(async () => {
    try {
      const cognitoUser = await getCurrentUser()
      const attributes = await fetchUserAttributes()

      const user: User = {
        id: cognitoUser.userId,
        username: cognitoUser.username,
        email: attributes.email || '',
        phoneNumber: attributes.phone_number,
        emailVerified: attributes.email_verified === 'true',
        phoneNumberVerified: attributes.phone_number_verified === 'true',
        status: 'ACTIVE',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      }

      setAuthState({
        isAuthenticated: true,
        isLoading: false,
        user,
        error: null
      })
    } catch {
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        error: null
      })
    }
  }, [])

  useEffect(() => {
    checkAuthStatus()
  }, [checkAuthStatus])

  const login = async (username: string, password: string) => {
    try {
      setAuthState(prev => ({ ...prev, isLoading: true, error: null }))
      await signIn({ username, password })

      // Debug: 打印 token 信息
      const session = await fetchAuthSession()
      console.log('=== Auth Tokens ===')
      console.log('Access Token:', session.tokens?.accessToken?.toString())
      console.log('ID Token:', session.tokens?.idToken?.toString())
      console.log('Access Token Payload:', session.tokens?.accessToken?.payload)
      console.log('ID Token Payload:', session.tokens?.idToken?.payload)
      console.log('===================')

      await checkAuthStatus()
    } catch (error) {
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error.message : '登录失败'
      }))
      throw error
    }
  }

  const register = async (_username: string, email: string, password: string) => {
    try {
      // Don't set global isLoading here - it would unmount the RegisterPage component
      // and reset the verification modal state
      setAuthState(prev => ({ ...prev, error: null }))
      const result = await authService.register(email, password)
      return result
    } catch (error) {
      setAuthState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : '注册失败'
      }))
      throw error
    }
  }

  const confirmRegistration = async (email: string, code: string) => {
    await authService.verifyEmail(email, code)
  }

  const resendVerificationCode = async (email: string) => {
    await authService.resendVerification(email)
  }

  const forgotPassword = async (email: string) => {
    await authService.forgotPassword(email)
  }

  const resetPassword = async (email: string, code: string, newPassword: string) => {
    await authService.resetPassword(email, code, newPassword)
  }

  const logout = async () => {
    try {
      await signOut()
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        error: null
      })
    } catch (error) {
      console.error('Logout error:', error)
    }
  }

  const value: AuthContextType = {
    ...authState,
    login,
    register,
    confirmRegistration,
    resendVerificationCode,
    forgotPassword,
    resetPassword,
    logout,
    refreshAuth: checkAuthStatus
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
