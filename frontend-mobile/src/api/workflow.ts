import request from './index'

export type DerivedTask = {
  task_no: string
  object_id: string
  source_instance_no?: string
  status?: string
  target_state?: string
}

export type PersonalMessage = {
  message_key: string
  title: string
  content: string
  event_at?: string
  unread?: boolean
  target?: string
}

export const workflowApi = {
  /** 重入库等派生任务（仅入库员/管理员/老板可读） */
  getDerivedTasks() {
    return request.get<any, { data: DerivedTask[] }>('/workflows/derived-tasks')
  },
  completeDerivedTask(taskNo: string, reason: string) {
    return request.post<any, { data: any }>(
      `/workflows/derived-tasks/${encodeURIComponent(taskNo)}/complete`,
      { reason },
    )
  },
  /** 个人消息盒子 */
  getPersonalMessages(params: { page?: number; limit?: number; unread?: boolean } = {}) {
    return request.get<any, { data: PersonalMessage[]; total: number; unread_count: number }>(
      '/workflows/personal-messages',
      { params },
    )
  },
  readPersonalMessage(messageKey: string) {
    return request.post('/workflows/personal-messages/read', { message_key: messageKey })
  },
  readAllPersonalMessages() {
    return request.post('/workflows/personal-messages/read-all')
  },
}
