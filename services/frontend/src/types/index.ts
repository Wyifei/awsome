export interface User {
  id: string
  username: string
  email: string
  phoneNumber?: string
  emailVerified: boolean
  phoneNumberVerified?: boolean
  createdAt: string
  updatedAt: string
}

export interface UserProfile {
  userId: string
  nickname?: string
  avatar?: string
  gender?: 'male' | 'female' | 'other'
  birthday?: string
  address?: string
  preferences?: Record<string, unknown>
}

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  user: User | null
  error: string | null
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}
