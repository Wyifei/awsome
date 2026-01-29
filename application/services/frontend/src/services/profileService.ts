import { api } from './api'
import type { UserProfile, AvatarResponse } from '../types'

/**
 * Profile Service - 用户资料管理相关 API
 * 调用 profile-service (/api/profiles)
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

export const profileService = {
  /**
   * 获取当前用户资料
   */
  getProfile: () => api.get<UserProfile>('/profiles/me'),

  /**
   * 获取头像图片 URL
   * @param userId 用户ID
   * @returns 完整的头像图片 URL
   */
  getAvatarUrl: (userId: string) => `${API_BASE_URL}/profiles/${userId}/avatar/image`,

  /**
   * 更新用户资料
   */
  updateProfile: (data: Partial<Omit<UserProfile, 'userId' | 'email' | 'username' | 'createdAt' | 'updatedAt'>>) =>
    api.put<UserProfile>('/profiles/me', data),

  /**
   * 上传头像
   */
  uploadAvatar: async (file: File): Promise<AvatarResponse> => {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.upload<AvatarResponse>('/profiles/me/avatar', formData)
    return response.data
  },

  /**
   * 删除头像
   */
  deleteAvatar: () => api.delete<void>('/profiles/me/avatar')
}
