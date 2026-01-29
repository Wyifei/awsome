import { fetchAuthSession } from 'aws-amplify/auth'
import type { ApiResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const session = await fetchAuthSession()
    const token = session.tokens?.idToken?.toString()
    if (token) {
      return { Authorization: `Bearer ${token}` }
    }
  } catch {
    // Not authenticated
  }
  return {}
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...options.headers
    }
  })

  const responseData = await response.json().catch(() => ({
    success: false,
    code: 'PARSE_ERROR',
    message: 'Failed to parse response'
  }))

  if (!response.ok) {
    throw new Error(responseData.message || `HTTP error! status: ${response.status}`)
  }

  return responseData
}

async function uploadRequest<T>(
  endpoint: string,
  formData: FormData
): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders()

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      ...authHeaders
      // Note: Don't set Content-Type for FormData, browser will set it with boundary
    },
    body: formData
  })

  const responseData = await response.json().catch(() => ({
    success: false,
    code: 'PARSE_ERROR',
    message: 'Failed to parse response'
  }))

  if (!response.ok) {
    throw new Error(responseData.message || `HTTP error! status: ${response.status}`)
  }

  return responseData
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: 'GET' }),

  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined
    }),

  put: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined
    }),

  delete: <T>(endpoint: string) => request<T>(endpoint, { method: 'DELETE' }),

  upload: <T>(endpoint: string, formData: FormData) => uploadRequest<T>(endpoint, formData)
}
