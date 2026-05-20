/**
 * 最大余数法(Largest Remainder Method / Hamilton 分配法)
 *
 * 把一组百分比数值各自四舍五入到整数,同时保证总和严格等于原始总和的舍入值
 * (通常为 100),避免直接 Math.round 导致 "80 + 19 + 1 = 101%" 这种误差。
 *
 * 算法:
 *   1. 每个值取 floor 得到待分配整数总和 sumFloor
 *   2. target = Math.round(所有输入之和)
 *   3. 按小数余数从大到小排序,把 (target - sumFloor) 个 1 依次分配给余数最大的项
 *
 * 改自岚图 voyah-voc utils/percent.ts(2026-05-08 借鉴),扩展支持 array 输入。
 */

interface RoundedItem {
  idx: number
  floor: number
  remainder: number
}

function _redistribute(items: RoundedItem[], target: number): RoundedItem[] {
  const currentSum = items.reduce((s, it) => s + it.floor, 0)
  let diff = target - currentSum

  if (diff > 0) {
    // 余数大的优先 +1;余数相同按原始顺序保持稳定
    const order = [...items].sort(
      (a, b) => b.remainder - a.remainder || a.idx - b.idx,
    )
    for (const it of order) {
      if (diff <= 0) break
      it.floor += 1
      diff -= 1
    }
  } else if (diff < 0) {
    // 极少出现:所有值之和已超过 target,余数小的优先 -1
    const order = [...items].sort(
      (a, b) => a.remainder - b.remainder || a.idx - b.idx,
    )
    for (const it of order) {
      if (diff >= 0) break
      if (it.floor > 0) {
        it.floor -= 1
        diff += 1
      }
    }
  }
  return items
}

/**
 * 数组版:输入百分比数组(总和 ≈ 100),返回总和严格 = round(总和) 的整数数组
 */
export function roundDistributionArray(values: number[]): number[] {
  if (!Array.isArray(values) || values.length === 0) return []
  const valid = values.map(v => (typeof v === 'number' && Number.isFinite(v) ? v : 0))
  const total = valid.reduce((s, v) => s + v, 0)
  const target = Math.round(total)
  const items: RoundedItem[] = valid.map((value, idx) => ({
    idx,
    floor: Math.floor(value),
    remainder: value - Math.floor(value),
  }))
  _redistribute(items, target)
  return items.sort((a, b) => a.idx - b.idx).map(it => it.floor)
}

/**
 * 字典版:输入百分比字典,返回 key 不变、value 严格相加 = round(总和) 的字典
 */
export function roundDistributionToHundred(
  distribution: Record<string, number> | undefined | null,
): Record<string, number> {
  if (!distribution) return {}
  const entries = Object.entries(distribution).filter(
    ([, v]) => typeof v === 'number' && Number.isFinite(v),
  )
  if (entries.length === 0) return {}

  const total = entries.reduce((sum, [, v]) => sum + v, 0)
  const target = Math.round(total)

  const items = entries.map(([, value], idx) => ({
    idx,
    floor: Math.floor(value),
    remainder: value - Math.floor(value),
  }))
  _redistribute(items, target)

  const result: Record<string, number> = {}
  for (let i = 0; i < entries.length; i++) {
    result[entries[i][0]] = items[i].floor
  }
  return result
}

/**
 * 把一组绝对值(任意单位)归一为百分比并保证总和严格 = 100
 *
 * 例:[450, 380, 170] → [45, 38, 17] (合计 100,而不是 99 或 101)
 */
export function normalizeToHundred(values: number[]): number[] {
  if (!Array.isArray(values) || values.length === 0) return []
  const total = values.reduce((s, v) => s + (Number(v) || 0), 0)
  if (total === 0) return values.map(() => 0)
  const pct = values.map(v => ((Number(v) || 0) / total) * 100)
  return roundDistributionArray(pct)
}
