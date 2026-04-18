const visitWithAuth = (path: string, role: string) => {
  cy.visit(path, {
    onBeforeLoad(win) {
      win.localStorage.setItem(
        'v7ex_auth',
        JSON.stringify({
          token: 'mock-token',
          rememberMe: true,
          userInfo: { username: 'tester', role, name: `${role} 用户` },
        }),
      )
    },
  })
}

describe('Role Guard Smoke', () => {
  it('blocks Sales from admin-only model dictionary page', () => {
    visitWithAuth('/model-dictionary', 'Sales')
    cy.location('pathname').should('eq', '/403')
    cy.contains('无权限').should('be.visible')
  })

  it('allows Boss to access model dictionary page', () => {
    cy.intercept('GET', '**/api/v1/model-dictionary/**', {
      statusCode: 200,
      body: { data: [{ id: 1, model_name: 'FR-400G', sort_order: 0, enabled: true, remark: '' }] },
    }).as('loadDictionary')

    visitWithAuth('/model-dictionary', 'Boss')
    cy.wait('@loadDictionary')
    cy.location('pathname').should('eq', '/model-dictionary')
    cy.contains('机型字典').should('be.visible')
  })

  it('redirects authenticated user away from login page', () => {
    cy.intercept('GET', '**/api/v1/inventory/**', {
      statusCode: 200,
      body: { data: [], total: 0, skip: 0, limit: 20 },
    }).as('loadInventory')

    visitWithAuth('/login?redirect=/inventory', 'Boss')
    cy.wait('@loadInventory')
    cy.location('pathname').should('eq', '/inventory')
  })
})
