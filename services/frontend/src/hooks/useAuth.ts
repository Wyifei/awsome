import { useState, useEffect, useCallback } from 'react'
import {
  getCurrentUser,
  signIn,
  signUp,
  signOut,
  confirmSignUp,
  fetchUserAttributes
} from 'aws-amplify/auth'
import type { AuthState, User } from '../types'

export function useAuth() {
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

  const register = async (username: string, email: string, password: string) => {
    try {
      setAuthState(prev => ({ ...prev, isLoading: true, error: null }))
      const result = await signUp({
        username,
        password,
        options: {
          userAttributes: { email }
        }
      })
      setAuthState(prev => ({ ...prev, isLoading: false }))
      return result
    } catch (error) {
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error.message : '注册失败'
      }))
      throw error
    }
  }

  const confirmRegistration = async (username: string, code: string) => {
    try {
      await confirmSignUp({ username, confirmationCode: code })
    } catch (error) {
      throw error
    }
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

  return {
    ...authState,
    login,
    register,
    confirmRegistration,
    logout,
    refreshAuth: checkAuthStatus
  }
}
