export interface User {
  id: string
  username: string
  email: string
  phoneNumber?: string
  emailVerified: boolean
  phoneNumberVerified?: boolean
  status: string
  createdAt: string
  updatedAt: string
}

export interface UserProfile {
  userId: string
  email: string
  username: string
  nickname?: string
  avatar?: string
  gender?: 'MALE' | 'FEMALE' | 'OTHER'
  birthday?: string
  address?: string
  createdAt?: string
  updatedAt?: string
}

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  user: User | null
  error: string | null
}

export interface ApiResponse<T> {
  success: boolean
  code: string
  message: string
  data: T
  timestamp: string
}

export interface AvatarResponse {
  success: boolean
  avatarUrl: string
}
