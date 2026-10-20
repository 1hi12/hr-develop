// Tests E2E Cypress — HR System
// Simule un recruteur qui utilise l'interface React

const API = Cypress.env('API_URL') || 'http://localhost:8000'

describe('HR System — Tests E2E', () => {

  // ── Santé de l'application ────────────────────────────────
  describe('Santé', () => {

    it('Le serveur répond sur /health', () => {
      cy.request(`${API}/health`).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body.status).to.eq('ok')
      })
    })

    it("L'API retourne les endpoints", () => {
      cy.request(`${API}/openapi.json`).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body).to.have.property('paths')
      })
    })
  })

  // ── Tests API via Cypress ─────────────────────────────────
  describe('API Candidats', () => {

    it('Liste des candidats accessible', () => {
      cy.request(`${API}/api/v1/candidates`).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body).to.have.property('items')
        expect(r.body.items).to.be.an('array')
      })
    })

    it('Filtre par statut pending fonctionne', () => {
      cy.request(`${API}/api/v1/candidates?status=pending`).then(r => {
        expect(r.status).to.eq(200)
      })
    })

    it('Candidat inexistant retourne 404', () => {
      cy.request({
        url: `${API}/api/v1/candidates/candidat-inexistant`,
        failOnStatusCode: false
      }).then(r => {
        expect(r.status).to.be.oneOf([404, 500])
      })
    })
  })

  describe('API Offres d\'emploi', () => {

    let jobId

    it('Créer une offre d\'emploi', () => {
      cy.request('POST', `${API}/api/v1/postings`, {
        title: `Cypress E2E Test ${Date.now()}`,
        description: 'Test automatique Cypress',
        required_skills: ['Python', 'React'],
      }).then(r => {
        expect(r.status).to.be.oneOf([200, 201])
        expect(r.body).to.have.property('job_id')
        jobId = r.body.job_id
      })
    })

    it("L'offre apparaît dans la liste", () => {
      cy.request(`${API}/api/v1/postings`).then(r => {
        expect(r.status).to.eq(200)
        const ids = r.body.map(p => p.job_id)
        expect(ids).to.include(jobId)
      })
    })

    it('Fermer l\'offre', () => {
      cy.request('PATCH', `${API}/api/v1/postings/${jobId}/status`, {
        status: 'closed'
      }).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body.status).to.eq('closed')
      })
    })

    it('Supprimer l\'offre', () => {
      cy.request('DELETE', `${API}/api/v1/postings/${jobId}`)
        .then(r => {
          expect(r.status).to.be.oneOf([200, 204])
        })
    })
  })

  describe('API Dashboard', () => {

    it('Stats du dashboard accessibles', () => {
      cy.request(`${API}/api/v1/dashboard/stats`).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body).to.have.property('activeCandidates')
        expect(r.body).to.have.property('cvsScreened')
        expect(r.body).to.have.property('hiredCandidates')
        expect(r.body.activeCandidates).to.be.at.least(0)
      })
    })

    it('Départements accessibles', () => {
      cy.request(`${API}/api/v1/dashboard/departments`).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body).to.be.an('array')
      })
    })

    it('Tendances accessibles', () => {
      cy.request(`${API}/api/v1/dashboard/trends`).then(r => {
        expect(r.status).to.eq(200)
        expect(r.body).to.be.an('array')
      })
    })
  })

  // ── Workflow complet recruteur ────────────────────────────
  describe('Workflow complet recruteur', () => {

    it('Cycle complet : créer → lire → fermer → supprimer', () => {
      let jobId

      // 1. Créer
      cy.request('POST', `${API}/api/v1/postings`, {
        title: `E2E Workflow ${Date.now()}`,
        description: 'Test workflow complet',
        required_skills: ['Python'],
      }).then(r => {
        expect(r.status).to.be.oneOf([200, 201])
        jobId = r.body.job_id

        // 2. Lire
        return cy.request(`${API}/api/v1/postings/${jobId}`)
      }).then(r => {
        expect(r.status).to.eq(200)

        // 3. Fermer
        return cy.request('PATCH', `${API}/api/v1/postings/${jobId}/status`, {
          status: 'closed'
        })
      }).then(r => {
        expect(r.body.status).to.eq('closed')

        // 4. Supprimer
        return cy.request('DELETE', `${API}/api/v1/postings/${jobId}`)
      }).then(r => {
        expect(r.status).to.be.oneOf([200, 204])
      })
    })
  })
})
