import axios from 'axios'

export const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

http.interceptors.response.use(
  (res) => {
    const data = res.data
    if (data && typeof data === 'object' && 'code' in data && data.code !== 0) {
      return Promise.reject(new Error(data.msg || '请求失败'))
    }
    return res
  },
  (err) => Promise.reject(err),
)
