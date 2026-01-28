import { api } from './api'
import type { User, UserProfile } from '../types'

export const userService = {
  getCurrentUser: () => api.get<User>('/users/me'),

  updateUser: (data: Partial<User>) => api.put<User>('/users/me', data),

  getProfile: () => api.get<UserProfile>('/users/me/profile'),

  updateProfile: (data: Partial<UserProfile>) => api.put<UserProfile>('/users/me/profile', data),

  changePassword: (oldPassword: string, newPassword: string) =>
    api.post<void>('/users/me/change-password', { oldPassword, newPassword }),

  deleteAccount: () => api.delete<void>('/users/me')
}
