/**
 * Auth Service - 调用 User Service 的认证相关 API
 * 注册和验证通过 User Service，登录仍通过 Cognito (Amplify)
 */

import { fetchAuthSession } from 'aws-amplify/auth'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

interface RegisterRequest {
  email: string
  password: string
}

interface VerifyEmailRequest {
  email: string
  code: string
}

interface ForgotPasswordRequest {
  email: string
}

interface ResetPasswordRequest {
  email: string
  code: string
  newPassword: string
}

interface ApiResponse<T = void> {
  success: boolean
  code: string
  message: string
  data: T
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    }
  })

  const responseData = await response.json().catch(() => ({
    success: false,
    code: 'PARSE_ERROR',
    message: '解析响应失败'
  }))

  if (!response.ok) {
    throw new Error(responseData.message || `请求失败: ${response.status}`)
  }

  return responseData
}

async function authenticatedRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const session = await fetchAuthSession()
  const token = session.tokens?.idToken?.toString()

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers
    }
  })

  const responseData = await response.json().catch(() => ({
    success: false,
    code: 'PARSE_ERROR',
    message: '解析响应失败'
  }))

  if (!response.ok) {
    throw new Error(responseData.message || `请求失败: ${response.status}`)
  }

  return responseData
}

export const authService = {
  /**
   * 注册新用户
   * 调用 User Service /api/users/register
   */
  register: async (email: string, password: string): Promise<ApiResponse> => {
    const data: RegisterRequest = { email, password }
    return request('/users/register', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  /**
   * 验证邮箱
   * 调用 User Service /api/users/verify-email
   */
  verifyEmail: async (email: string, code: string): Promise<ApiResponse> => {
    const data: VerifyEmailRequest = { email, code }
    return request('/users/verify-email', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  /**
   * 重新发送验证码
   * 调用 User Service /api/users/resend-verification
   */
  resendVerification: async (email: string): Promise<ApiResponse> => {
    return request('/users/resend-verification', {
      method: 'POST',
      body: JSON.stringify({ email })
    })
  },

  /**
   * 忘记密码 - 发送重置验证码
   * 调用 User Service /api/users/forgot-password
   */
  forgotPassword: async (email: string): Promise<ApiResponse> => {
    const data: ForgotPasswordRequest = { email }
    return request('/users/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  /**
   * 重置密码
   * 调用 User Service /api/users/reset-password
   */
  resetPassword: async (email: string, code: string, newPassword: string): Promise<ApiResponse> => {
    const data: ResetPasswordRequest = { email, code, newPassword }
    return request('/users/reset-password', {
      method: 'POST',
      body: JSON.stringify(data)
    })
  },

  /**
   * 发送注销账号验证码
   * 调用 User Service /api/users/delete-account/send-code
   */
  sendDeleteAccountCode: async (email: string): Promise<ApiResponse> => {
    return authenticatedRequest('/users/delete-account/send-code', {
      method: 'POST',
      body: JSON.stringify({ email })
    })
  },

  /**
   * 确认注销账号
   * 调用 User Service /api/users/delete-account/confirm
   */
  deleteAccount: async (email: string, code: string): Promise<ApiResponse> => {
    return authenticatedRequest('/users/delete-account/confirm', {
      method: 'POST',
      body: JSON.stringify({ email, code })
    })
  }
}
