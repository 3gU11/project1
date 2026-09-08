import { describe, expect, it } from 'vitest'
import {
  areProductionGroupsCompatible,
  productionGroupOfCategory,
  productionGroupOfModel,
  productionRegionOfCategory,
} from '../src/utils/sandboxCategory'

describe('sandbox production compatibility groups', () => {
  it('allows large XS and AUTO to share the same production group', () => {
    expect(productionGroupOfCategory('中大型XS')).toBe('LARGE')
    expect(productionGroupOfCategory('中大型AUTO')).toBe('LARGE')
    expect(areProductionGroupsCompatible('中大型XS', '中大型AUTO')).toBe(true)
  })

  it('keeps small and large machines isolated', () => {
    expect(areProductionGroupsCompatible('中小型XS', '中大型XS')).toBe(false)
    expect(areProductionGroupsCompatible('中小型AUTO', '中大型AUTO')).toBe(false)
  })

  it('maps production groups to physical line regions', () => {
    expect(productionRegionOfCategory('中大型AUTO')).toBe('LARGE')
    expect(productionRegionOfCategory('中小型XS')).toBe('SMALL')
    expect(productionRegionOfCategory('特殊')).toBe('SPECIAL')
  })

  it('classifies concrete large models consistently', () => {
    expect(productionGroupOfModel('FR-7055XS(PRO)')).toBe('LARGE')
    expect(productionGroupOfModel('FR-8055AUTO')).toBe('LARGE')
    expect(productionGroupOfModel('FR-400AUTO')).toBe('SMALL_AUTO')
  })
})
