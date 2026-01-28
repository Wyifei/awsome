import { api } from './api'
import type { User } from '../types'

/**
 * User Service - 用户身份管理相关 API
 * 调用 user-service (/api/users)
 */
export const userService = {
  /**
   * 获取当前用户身份信息
   */
  getCurrentUser: () => api.get<User>('/users/me'),

  /**
   * 修改密码
   */
  changePassword: (oldPassword: string, newPassword: string) =>
    api.post<void>('/users/me/change-password', { oldPassword, newPassword }),

  /**
   * 注销账户
   */
  deleteAccount: () => api.delete<void>('/users/me')
}
