describe('Performance Smoke', () => {
  it('login page domContentLoaded under 2s', () => {
    cy.visit('/login')
    cy.window().then((win) => {
      const nav = win.performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
      expect(nav, 'navigation entry exists').to.exist
      if (!nav) return
      expect(nav.domContentLoadedEventEnd, 'DCL(ms)').to.be.lessThan(2000)
    })
  })
})
