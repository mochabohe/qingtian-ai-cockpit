// sessionStorage 缓存工具: TTL + 自动 JSON 序列化
// 用于"打开慢、内容不会瞬变"的接口结果(数据体检/字段画像/VOC 聚类等),
// 演示场景一次会话内反复打开同一弹窗时秒回。
//
// 使用:
//   const data = readCache<MyType>('health:sales_records')
//   if (data) return data
//   const fresh = await http.get(...)
//   writeCache('health:sales_records', fresh)

const DEFAULT_TTL_MS = 10 * 60 * 1000  // 10 分钟

export function readCache<T = any>(key: string, ttlMs = DEFAULT_TTL_MS): T | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const { ts, data } = JSON.parse(raw)
    if (Date.now() - ts > ttlMs) {
      sessionStorage.removeItem(key)
      return null
    }
    return data as T
  } catch {
    return null
  }
}

export function writeCache(key: string, data: any) {
  try {
    sessionStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }))
  } catch {
    // 配额满 / 隐身模式 → 静默
  }
}
