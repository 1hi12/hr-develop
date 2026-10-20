const { defineConfig } = require('cypress')

module.exports = defineConfig({
  e2e: {
    baseUrl: process.env.CYPRESS_BASE_URL || 'http://localhost:8000',
    specPattern: 'cypress/e2e/**/*.cy.js',
    screenshotsFolder: 'reports/cypress/screenshots',
    videosFolder: 'reports/cypress/videos',
    supportFile: false,
    env: {
      API_URL: process.env.CYPRESS_BASE_URL || 'http://localhost:8000',
    },
  },
})
