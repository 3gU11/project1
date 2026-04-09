describe('Auth and Guard Smoke', () => {
  it('shows login page', () => {
    cy.visit('/login')
    cy.contains('V7ex 成品管理系统').should('be.visible')
    cy.contains('登录').should('be.visible')
  })

  it('redirects protected route to login when unauthenticated', () => {
    cy.clearAllLocalStorage()
    cy.visit('/inventory')
    cy.location('pathname').should('eq', '/login')
  })
})
