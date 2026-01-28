import { useState, useEffect, useCallback } from 'react'
import {
  getCurrentUser,
  signIn,
  signOut,
  fetchUserAttributes
} from 'aws-amplify/auth'
import { authService } from '../services/authService'
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

  /**
   * 注册新用户 - 调用 User Service API
   * 注册成功后会发送验证码到用户邮箱
   */
  const register = async (_username: string, email: string, password: string) => {
    try {
      setAuthState(prev => ({ ...prev, isLoading: true, error: null }))
      // 调用 User Service 注册 API
      const result = await authService.register(email, password)
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

  /**
   * 验证邮箱 - 调用 User Service API
   */
  const confirmRegistration = async (email: string, code: string) => {
    try {
      await authService.verifyEmail(email, code)
    } catch (error) {
      throw error
    }
  }

  /**
   * 重新发送验证码
   */
  const resendVerificationCode = async (email: string) => {
    try {
      await authService.resendVerification(email)
    } catch (error) {
      throw error
    }
  }

  /**
   * 忘记密码 - 发送重置验证码
   */
  const forgotPassword = async (email: string) => {
    try {
      await authService.forgotPassword(email)
    } catch (error) {
      throw error
    }
  }

  /**
   * 重置密码
   */
  const resetPassword = async (email: string, code: string, newPassword: string) => {
    try {
      await authService.resetPassword(email, code, newPassword)
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
    resendVerificationCode,
    forgotPassword,
    resetPassword,
    logout,
    refreshAuth: checkAuthStatus
  }
}
